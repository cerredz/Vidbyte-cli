"""Sequential task-board execution over separate Codex agents with summaries.

The board owns ordering and windowed context. The SDK owns each task turn.
Raw prior results never reach the next agent; only bounded summaries do.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import TaskBoardResult, TaskBoardSettings, TaskBoardStepResult
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

    def render_prompt(self, task: str, index: int, context: str) -> str:
        # Renders current task plus windowed summaries with no template injection.
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
        # Loops tasks in order, each in a fresh agent with windowed summaries.
        summaries: list[str] = []
        threads: list[str] = []
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
                threads.append("")
                continue
            completed += 1
            summaries.append(summary[0])
            threads.append(summary[1])
            steps.append(self._completed_step(task, index, summary[0], summary[1]))
        self._progress(Progress.COMPLETE)
        return self._result(admission_id, completed, failed, steps)

    async def _run_task(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> tuple[str, str] | None:
        # Retries one task with identical context before marking it failed.
        attempts = settings.max_retries_per_task + 1
        for attempt in range(attempts):
            if attempt > 0:
                self._progress(Progress.TASK_RETRYING)
            outcome = await self._attempt(task, index, summaries, settings)
            if outcome is not None:
                return outcome
        return None

    async def _attempt(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> tuple[str, str] | None:
        # Executes one attempt in a fresh agent and returns summary plus thread.
        try:
            agent = self._build_agent(index)
            prompt = self._build_prompt(task, index, summaries, settings)
            reply = await self._turn(agent, prompt)
            text = self._completed_text(reply)
            thread = self._thread_id(reply)
            summary = self._summarizer.summarize(
                text, settings.summary_mode.value, settings.summary_max_chars
            )
            return (summary, thread)
        except Exception:
            return None

    def _build_prompt(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> str:
        # Selects the window slice then renders the bounded prompt.
        windowed = self._summarizer.windowed(summaries, index, settings.window)
        context = self._summarizer.render_context(windowed)
        return self._summarizer.render_prompt(task, index, context)

    def _build_agent(self, index: int) -> CodexHarnessAgent:
        # Constructs a fresh agent so threads never leak across tasks.
        from vidbyte.agents.codex import CodexHarnessAgent
        from vidbyte.lib.dataclasses.codex import (
            CodexAgentSettings,
            CodexHarnessAgentSettings,
            CodexThreadSettings,
        )
        from vidbyte.lib.enums.codex import CodexSandbox

        client = self._client_settings()
        return CodexHarnessAgent(
            CodexHarnessAgentSettings(
                name=f"task-board-{index}",
                system_prompt=self._prompt(),
                codex=CodexAgentSettings(
                    client=client, thread=CodexThreadSettings(sandbox=CodexSandbox.WORKSPACE_WRITE)
                ),
            )
        )

    def _client_settings(self) -> object:
        # Builds child-only client config from the prepared plan paths.
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        return CodexClientSettings(
            codex_bin=self._executable,
            cwd=self._working_directory,
            env=self._environment,
            config_overrides=tuple(s.value for s in TaskBoardCodexConfig),
        )

    async def _turn(self, agent: CodexHarnessAgent, prompt: str) -> AgentMessage:
        # Cancels slow turns so the SDK client unwinds before continuing.
        from vidbyte.lib.dataclasses.codex import CodexRunInput

        try:
            async with asyncio.timeout(TaskBoardLimit.TURN_TIMEOUT_SECONDS):
                return await agent.arun(CodexRunInput.text(prompt))
        except (TimeoutError, Exception) as error:
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
