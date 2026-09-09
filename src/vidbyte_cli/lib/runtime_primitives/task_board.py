"""Sequential task-board execution over separate Codex agents with summaries.

The board owns ordering and context. The SDK owns each task turn. Raw prior results never
reach the next agent; a windowed board forwards bounded summaries and an isolated board
forwards nothing at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import (
    TaskBoardCheckpoint,
    TaskBoardContextMode,
    TaskBoardResult,
    TaskBoardSettings,
    TaskBoardStepResult,
)
from ..constants.runtime import TaskBoardCodexConfig, TaskBoardLimit
from ..constants.runtime import TaskBoardProgress as Progress
from ..errors.failures import TaskBoardCheckpointMismatch, TaskBoardHostFailed
from .task_board_checkpoints import TaskBoardCheckpointer

if TYPE_CHECKING:
    from vidbyte.agents.codex import CodexHarnessAgent
    from vidbyte.agents.types import AgentMessage


class TaskBoardSummarizer:
    """Builds bounded summaries and per-task prompts without network calls."""

    def summarize(self, text: str, mode: str, limit: int) -> str:
        # Shrinks one result deterministically so prompts stay bounded.
        cleaned = text.strip()
        if len(cleaned) <= limit:
            return cleaned
        if mode == "head-tail":
            return self._head_tail(cleaned, limit)
        return self._truncate_tail(cleaned, limit)

    def render_context(self, summaries: tuple[tuple[int, str], ...]) -> str:
        # Labels each prior summary so agents cannot confuse board order.
        return "\n".join(f"[{index}] {summary}" for index, summary in summaries)

    def render_prompt(self, task: str, index: int, context: str | None) -> str:
        # A None context is an isolated board: the prior-results section is absent, not
        # merely empty, so no agent can infer that earlier work exists to be reconciled.
        if context is None:
            return f"Task {index}: {task}\n\nComplete only this task."
        prior = context if context.strip() else "(no prior results)"
        return f"Task {index}: {task}\n\nPrior summaries:\n{prior}\n\nComplete only this task."

    def windowed(
        self, summaries: list[str], index: int, window: int
    ) -> tuple[tuple[int, str], ...]:
        # Slices the trailing window so task N sees exactly N-window..N-1.
        start = max(0, index - window)
        return tuple((start + offset, value) for offset, value in enumerate(summaries[start:index]))

    def _truncate_tail(self, text: str, limit: int) -> str:
        # Keeps a prefix and names how much was removed.
        removed = len(text) - limit
        return f"{text[:limit]}...[truncated {removed} chars]"

    def _head_tail(self, text: str, limit: int) -> str:
        # Keeps head plus tail evenly so endings survive summarization.
        half = limit // 2
        rest = limit - half
        removed = len(text) - limit
        return f"{text[:half]}...[truncated {removed} chars]...{text[len(text) - rest :]}"


class TaskBoardCodexSession:
    """One board invocation's environment and per-task SDK agents."""

    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None:
        # Stores env and progress without starting any agent turn.
        self._environment = dict(environment)
        self._progress = progress
        self._executable = ""
        self._working_directory = ""
        self._summarizer = TaskBoardSummarizer()
        self._checkpointer: TaskBoardCheckpointer | None = None
        self._start_from = 0
        self._replay_index: int | None = None

    def with_resume(self, checkpointer: TaskBoardCheckpointer, start_from: int) -> None:
        # Arms prefix loading so the run continues from stored steps instead of index 0.
        self._checkpointer = checkpointer
        self._start_from = start_from

    def with_replay(self, checkpointer: TaskBoardCheckpointer, index: int) -> None:
        # Arms single-step re-execution with the exact stored prompt for debugging.
        self._checkpointer = checkpointer
        self._replay_index = index

    def prepare(self, plan: Plan) -> None:
        # Loads the SDK and records paths without starting a paid model turn.
        from vidbyte.agents.codex import CodexHarnessAgent  # noqa: F401

        self._executable = str(plan.executable)
        self._working_directory = str(plan.working_directory)

    def run(self, plan: Plan, settings: TaskBoardSettings, admission_id: str) -> TaskBoardResult:
        # Runs the ordered board synchronously for command-layer callers.
        try:
            if self._replay_index is not None:
                return asyncio.run(self._replay(plan, settings, admission_id, self._replay_index))
            return asyncio.run(self._run(plan, settings, admission_id))
        except TaskBoardHostFailed:
            raise
        except (TimeoutError, RuntimeError) as error:
            raise TaskBoardHostFailed() from error

    async def _run(
        self, plan: Plan, settings: TaskBoardSettings, admission_id: str
    ) -> TaskBoardResult:
        # Loops tasks in order, each in a fresh agent, appending one summary per attempted
        # task so board indices and the window slice stay aligned even across failures.
        summaries: list[str] = []
        steps: list[TaskBoardStepResult] = []
        completed = 0
        failed = 0
        self._progress(Progress.TASK_STARTING)
        start, completed, failed = self._load_prefix(summaries, steps, settings)
        for index in range(start, len(settings.tasks)):
            task = settings.tasks[index]
            outcome = await self._run_task(task, index, summaries, settings)
            if outcome is None:
                failed += 1
                failed_step = self._failed_step(task, index)
                steps.append(failed_step)
                prompt = self._build_prompt(task, index, summaries, settings)
                self._save(failed_step, prompt, admission_id, None)
                if settings.stop_on_error:
                    break
                summaries.append(f"Task {index} failed.")
                continue
            completed += 1
            done = self._completed_step(task, index, outcome[0], outcome[1])
            summaries.append(outcome[0])
            steps.append(done)
            self._save(done, outcome[2], admission_id, outcome[3])
        self._progress(Progress.COMPLETE)
        return self._result(admission_id, completed, failed, steps)

    def _load_prefix(
        self, summaries: list[str], steps: list[TaskBoardStepResult], settings: TaskBoardSettings
    ) -> tuple[int, int, int]:
        # Seeds window and results from stored steps; a fresh run only stamps the manifest.
        if self._checkpointer is None:
            return (0, 0, 0)
        if self._start_from > len(settings.tasks):
            raise TaskBoardCheckpointMismatch("resume-past-end")
        if self._start_from == 0:
            try:
                self._checkpointer.write_manifest(settings)
            except Exception:
                self._progress("Checkpoint manifest write failed; continuing.")
            return (0, 0, 0)
        self._checkpointer.validate_manifest(settings)
        prefix = self._checkpointer.load_prefix(self._start_from)
        self._append_prefix(summaries, steps, prefix)
        completed = sum(1 for record in prefix if record.status == "completed")
        failed = sum(1 for record in prefix if record.status == "failed")
        return (len(prefix), completed, failed)

    @staticmethod
    def _append_prefix(
        summaries: list[str],
        steps: list[TaskBoardStepResult],
        prefix: tuple[TaskBoardCheckpoint, ...],
    ) -> int:
        # Replays stored summaries and step records so indices stay aligned with a fresh run.
        for record in prefix:
            summaries.append(record.summary)
            steps.append(
                TaskBoardStepResult(
                    index=record.index,
                    task=record.task,
                    summary=record.summary,
                    status=record.status,
                    thread_id=record.thread_id,
                )
            )
        return len(prefix)

    async def _replay(
        self, plan: Plan, settings: TaskBoardSettings, admission_id: str, index: int
    ) -> TaskBoardResult:
        # Rebuilds one step's exact prompt from stored summaries and runs only that step.
        del plan
        checkpointer = self._require_checkpointer()
        if index >= len(settings.tasks):
            raise TaskBoardCheckpointMismatch("replay-past-end")
        checkpointer.validate_manifest(settings)
        summaries: list[str] = []
        steps: list[TaskBoardStepResult] = []
        self._progress(Progress.TASK_STARTING)
        self._append_prefix(summaries, steps, checkpointer.load_prefix(index))
        task = settings.tasks[index]
        outcome = await self._run_task(task, index, summaries, settings)
        if outcome is None:
            replayed = self._failed_step(task, index)
            prompt = self._build_prompt(task, index, summaries, settings)
            self._save(replayed, prompt, admission_id, None)
            result = self._result(admission_id, 0, 1, [replayed])
        else:
            replayed = self._completed_step(task, index, outcome[0], outcome[1])
            self._save(replayed, outcome[2], admission_id, outcome[3])
            result = self._result(admission_id, 1, 0, [replayed])
        self._progress(Progress.COMPLETE)
        return result

    def _require_checkpointer(self) -> TaskBoardCheckpointer:
        # Resume and replay are unreachable without one; the command arms it first.
        if self._checkpointer is None:
            raise RuntimeError("task board resume requested without a checkpointer")
        return self._checkpointer

    def _save(
        self, step: TaskBoardStepResult, prompt: str, admission_id: str, tokens: int | None
    ) -> None:
        # Persists one step without ever failing it; spend stays None until budgets land.
        if self._checkpointer is None:
            return
        record = TaskBoardCheckpoint(
            index=step.index,
            task=step.task,
            prompt=prompt,
            summary=step.summary,
            status=step.status,
            thread_id=step.thread_id,
            total_tokens=tokens,
            estimated_cost_usd=None,
            admission_id=admission_id,
            created_at=TaskBoardCheckpointer.timestamp(),
        )
        try:
            self._checkpointer.write_step(record)
        except Exception:
            self._progress(f"Checkpoint write failed for task {step.index}; continuing.")

    async def _run_task(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> tuple[str, str, str, int | None] | None:
        # One task start to finish. Every attempt builds its own agent and renders the same
        # prompt, so a retry recovers from a dead host rather than re-deciding the context.
        for attempt in range(settings.max_retries_per_task + 1):
            if attempt > 0:
                self._progress(Progress.TASK_RETRYING)
            try:
                prompt = self._build_prompt(task, index, summaries, settings)
                reply = await self._turn(self._build_agent(index), prompt)
                thread = self._thread_id(reply)
                summary = self._summarizer.summarize(
                    self._completed_text(reply),
                    settings.summary_mode.value,
                    settings.summary_max_chars,
                )
                return (summary, thread, prompt, self._usage_of(reply))
            except Exception:
                # Attempt failures stay local: stop-on-error is the caller's policy.
                continue
        return None

    def _usage_of(self, reply: AgentMessage) -> int | None:
        # Reads cumulative provider tokens when reported; unknown usage is None, never zero.
        data = reply.codex
        if data is None or not getattr(data, "usage_available", False):
            return None
        total = getattr(data.usage, "total_tokens", None)
        return total if isinstance(total, int) and total >= 0 else None

    def _build_prompt(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> str:
        # An isolated board hands its agents no prior-results channel at all; a windowed board
        # renders exactly the trailing slice the window admits and nothing older.
        if settings.context_mode is TaskBoardContextMode.ISOLATED:
            return self._summarizer.render_prompt(task, index, None)
        windowed = self._summarizer.windowed(summaries, index, settings.window)
        context = self._summarizer.render_context(windowed)
        return self._summarizer.render_prompt(task, index, context)

    def _build_agent(self, index: int) -> CodexHarnessAgent:
        # Constructs a fresh agent so threads never leak across tasks. The client config is
        # built here rather than in a helper because its type only exists under this import.
        from vidbyte.agents.codex import CodexHarnessAgent
        from vidbyte.lib.dataclasses.codex import (
            CodexAgentSettings,
            CodexClientSettings,
            CodexHarnessAgentSettings,
            CodexThreadSettings,
        )
        from vidbyte.lib.enums.codex import CodexSandbox

        client = CodexClientSettings(
            codex_bin=self._executable,
            cwd=self._working_directory,
            env=self._environment,
            config_overrides=tuple(setting.value for setting in TaskBoardCodexConfig),
        )
        return CodexHarnessAgent(
            CodexHarnessAgentSettings(
                name=f"task-board-{index}",
                system_prompt=self._prompt(),
                codex=CodexAgentSettings(
                    client=client, thread=CodexThreadSettings(sandbox=CodexSandbox.WORKSPACE_WRITE)
                ),
            )
        )

    async def _turn(self, agent: CodexHarnessAgent, prompt: str) -> AgentMessage:
        # Cancels slow turns so the SDK client unwinds before continuing.
        from vidbyte.lib.dataclasses.codex import CodexRunInput

        try:
            async with asyncio.timeout(TaskBoardLimit.TURN_TIMEOUT_SECONDS):
                return await agent.arun(CodexRunInput.text(prompt))
        except Exception as error:
            # This covers the timeout too, which asyncio raises as a plain TimeoutError.
            raise TaskBoardHostFailed() from error

    def _completed_text(self, reply: AgentMessage) -> str:
        # Rejects incomplete turns without exposing model content in errors.
        data = reply.codex
        if data is None or data.status != "completed" or not data.final_response:
            raise TaskBoardHostFailed()
        return str(reply.content)

    def _thread_id(self, reply: AgentMessage) -> str:
        # Requires a stable thread identity for per-step accounting.
        data = reply.codex
        thread = str(data.thread_id) if data is not None else ""
        if not thread.strip():
            raise TaskBoardHostFailed()
        return thread

    def _completed_step(
        self, task: str, index: int, summary: str, thread: str
    ) -> TaskBoardStepResult:
        # Records one successful step with its bounded summary.
        return TaskBoardStepResult(
            index=index, task=task, summary=summary, status="completed", thread_id=thread
        )

    def _failed_step(self, task: str, index: int) -> TaskBoardStepResult:
        # Records one failed step with a static placeholder summary.
        return TaskBoardStepResult(
            index=index,
            task=task,
            summary=f"Task {index} failed.",
            status="failed",
            thread_id=f"task-board-{index}-failed",
        )

    def _result(
        self, admission_id: str, completed: int, failed: int, steps: list[TaskBoardStepResult]
    ) -> TaskBoardResult:
        # Joins step summaries into the board-level text output.
        text = "\n".join(f"[{step.index}] {step.summary}" for step in steps)
        return TaskBoardResult(
            admission_id=admission_id,
            completed=completed,
            failed=failed,
            steps=tuple(steps),
            text=text,
        )

    def _prompt(self) -> str:
        # Loads the fixed stage prompt for every board task agent.
        return files(__package__).joinpath("task_board_system.md").read_text(encoding="utf-8")
