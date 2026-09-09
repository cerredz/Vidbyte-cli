"""Sequential task-board execution over separate Codex agents with summaries.

The board owns ordering and context. The SDK owns each task turn. Raw prior results never
reach the next agent; a windowed board forwards bounded summaries and an isolated board
forwards nothing at all.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import (
    TaskBoardContextMode,
    TaskBoardResult,
    TaskBoardSettings,
    TaskBoardStepResult,
)
from ..constants.runtime import TaskBoardCodexConfig, TaskBoardLimit
from ..constants.runtime import TaskBoardProgress as Progress
from ..errors.failures import TaskBoardHostFailed

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

    def render_decompose_prompt(self, task: str, index: int, max_subtasks: int) -> str:
        # An isolated decompose prompt carries only the agent's own task plus the tool
        # contract, so sibling tasks can never leak into placement decisions.
        return (
            f"Task {index}: {task}\n\nComplete this task. You see only this task.\n\n"
            "Decompose contract: optionally replace this task with an array of 2 to "
            f"{max_subtasks} self-contained subtasks at this same index. Append one "
            "```decompose fenced block holding a JSON array of subtask strings, e.g.\n"
            '```decompose\n["first subtask", "second subtask"]\n```\n'
            "Each subtask runs as its own isolated task and cannot decompose further. "
            "Omit the block to keep this task as one unit of work."
        )

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


class TaskBoardDecomposeParser:
    """Reads one fenced decompose block from agent text without network calls."""

    _OPEN = "```decompose"
    _CLOSE = "```"

    def parse_final_text(self, text: str, max_subtasks: int) -> tuple[str, ...]:
        # Returns validated subtasks, or empty when the agent did not decompose.
        block = self.extract_block(text)
        if block is None:
            return ()
        return self.clean_candidates(self._decode_block(block), max_subtasks)

    def strip_block(self, text: str) -> str:
        # Removes the decompose block so stored summaries hold only outcome text.
        start = text.find(self._OPEN)
        if start < 0:
            return text
        end = text.find(self._CLOSE, start + len(self._OPEN))
        if end < 0:
            return text[:start].rstrip()
        return (text[:start] + text[end + len(self._CLOSE) :]).strip()

    def extract_block(self, text: str) -> str | None:
        # Takes the first fenced block; later blocks are ignored, never merged.
        start = text.find(self._OPEN)
        if start < 0:
            return None
        end = text.find(self._CLOSE, start + len(self._OPEN))
        if end < 0:
            return None
        return text[start + len(self._OPEN) : end].strip()

    def clean_candidates(self, candidates: list[str], max_subtasks: int) -> tuple[str, ...]:
        # Drops empties, over-long entries, and duplicates, then caps the count.
        seen: set[str] = set()
        kept: list[str] = []
        for candidate in candidates:
            cleaned = candidate.strip()
            if not cleaned or len(cleaned) > TaskBoardLimit.MAX_TASK_CHARS:
                continue
            folded = cleaned.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            kept.append(cleaned)
            if len(kept) >= max_subtasks:
                break
        if len(kept) < TaskBoardLimit.MIN_SUBTASKS:
            return ()
        return tuple(kept)

    def _decode_block(self, block: str) -> list[str]:
        # Accepts only a JSON array; objects, scalars, and bad JSON mean no split.
        try:
            decoded = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(decoded, list):
            return []
        return [item for item in decoded if isinstance(item, str)]


class TaskBoardCodexSession:
    """One board invocation's environment and per-task SDK agents."""

    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None:
        # Stores env and progress without starting any agent turn.
        self._environment = dict(environment)
        self._progress = progress
        self._executable = ""
        self._working_directory = ""
        self._summarizer = TaskBoardSummarizer()

    def prepare(self, plan: Plan) -> None:
        # Loads the SDK and records paths without starting a paid model turn.
        from vidbyte.agents.codex import CodexHarnessAgent  # noqa: F401

        self._executable = str(plan.executable)
        self._working_directory = str(plan.working_directory)

    def run(self, plan: Plan, settings: TaskBoardSettings, admission_id: str) -> TaskBoardResult:
        # Runs the ordered board synchronously for command-layer callers.
        try:
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
        if settings.allow_decompose:
            return await self._run_decomposing(plan, settings, admission_id)
        summaries: list[str] = []
        steps: list[TaskBoardStepResult] = []
        completed = 0
        failed = 0
        self._progress(Progress.TASK_STARTING)
        for index, task in enumerate(settings.tasks):
            summary = await self._run_task(task, index, summaries, settings)
            if summary is None:
                failed += 1
                steps.append(self._failed_step(task, index))
                if settings.stop_on_error:
                    break
                summaries.append(f"Task {index} failed.")
                continue
            completed += 1
            summaries.append(summary[0])
            steps.append(self._completed_step(task, index, summary[0], summary[1]))
        self._progress(Progress.COMPLETE)
        return self._result(admission_id, completed, failed, steps)

    async def _run_decomposing(
        self, plan: Plan, settings: TaskBoardSettings, admission_id: str
    ) -> TaskBoardResult:
        # Walks a mutable board where a parent is replaced in place by its subtasks.
        _ = plan
        work: list[str] = list(settings.tasks)
        depths: list[int] = [0] * len(work)
        parser = TaskBoardDecomposeParser()
        summaries: list[str] = []
        steps: list[TaskBoardStepResult] = []
        completed = 0
        failed = 0
        self._progress(Progress.TASK_STARTING)
        index = 0
        while index < len(work):
            task = work[index]
            outcome = await self._run_task(task, index, summaries, settings)
            if outcome is None:
                failed += 1
                steps.append(self._failed_step(task, index))
                if settings.stop_on_error:
                    break
                summaries.append(f"Task {index} failed.")
                index += 1
                continue
            full_text = outcome[2]
            children = parser.parse_final_text(full_text, settings.max_subtasks)
            if depths[index] > 0:
                children = ()
            room = int(TaskBoardLimit.MAX_TASKS) - len(work) + 1
            if room < len(children):
                children = children[:room]
            if len(children) >= TaskBoardLimit.MIN_SUBTASKS:
                work[index : index + 1] = list(children)
                depths[index : index + 1] = [1] * len(children)
                completed += 1
                summaries.append(f"Task {index} decomposed into {len(children)} subtasks.")
                steps.append(self._decomposed_step(task, index, len(children), outcome[1]))
                continue
            cleaned = parser.strip_block(full_text)
            summary = self._summarizer.summarize(
                cleaned, settings.summary_mode.value, settings.summary_max_chars
            )
            completed += 1
            summaries.append(summary)
            steps.append(self._completed_step(task, index, summary, outcome[1]))
            index += 1
        self._progress(Progress.COMPLETE)
        return self._result(admission_id, completed, failed, steps)

    async def _run_task(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> tuple[str, str, str] | None:
        # One task start to finish. Every attempt builds its own agent and renders the same
        # prompt, so a retry recovers from a dead host rather than re-deciding the context.
        for attempt in range(settings.max_retries_per_task + 1):
            if attempt > 0:
                self._progress(Progress.TASK_RETRYING)
            try:
                prompt = self._build_prompt(task, index, summaries, settings)
                reply = await self._turn(self._build_agent(index), prompt)
                thread = self._thread_id(reply)
                full_text = self._completed_text(reply)
                summary = self._summarizer.summarize(
                    full_text,
                    settings.summary_mode.value,
                    settings.summary_max_chars,
                )
                return (summary, thread, full_text)
            except Exception:
                # Attempt failures stay local: stop-on-error is the caller's policy.
                continue
        return None

    def _build_prompt(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> str:
        # A decompose board is always isolated: each agent sees only its own task plus
        # the tool contract, so window and summary settings never shape its prompt.
        if settings.allow_decompose:
            return self._summarizer.render_decompose_prompt(task, index, settings.max_subtasks)
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

    def _decomposed_step(
        self, task: str, index: int, count: int, thread: str
    ) -> TaskBoardStepResult:
        # Records a parent whose work was expanding into subtasks at its own index.
        return TaskBoardStepResult(
            index=index,
            task=task,
            summary=f"Task {index} decomposed into {count} subtasks.",
            status="completed",
            thread_id=thread,
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
