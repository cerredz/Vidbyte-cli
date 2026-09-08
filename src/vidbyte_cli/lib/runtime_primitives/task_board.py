"""Task-board execution over separate Codex agents with summaries.

The board owns ordering and context. The SDK owns each task turn. Raw prior results never
reach the next agent; a linear board forwards windowed summaries, a DAG board forwards only
direct dependencies' summaries, and an isolated board forwards nothing at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import (
    TaskBoardContextMode,
    TaskBoardExecutionType,
    TaskBoardResult,
    TaskBoardSettings,
    TaskBoardStepResult,
)
from ..constants.runtime import TaskBoardCodexConfig, TaskBoardLimit
from ..constants.runtime import TaskBoardProgress as Progress
from ..errors.failures import TaskBoardDependencyInvalid, TaskBoardHostFailed

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
        # Delegates to the loop the execution type selects; linear order is preserved exactly.
        if settings.execution_type is TaskBoardExecutionType.DAG:
            return await self._run_dag(plan, settings, admission_id)
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

    async def _run_dag(
        self, plan: Plan, settings: TaskBoardSettings, admission_id: str
    ) -> TaskBoardResult:
        # Runs each task once in topological order with dependency-only context.
        _ = plan
        order = self._topological_order(len(settings.tasks), settings.dependencies)
        slots: list[str] = ["" for _ in settings.tasks]
        failed: set[int] = set()
        steps: list[TaskBoardStepResult] = []
        completed = 0
        uncompleted = 0
        self._progress(Progress.TASK_STARTING)
        parents = self._dag_parents(settings)
        for index in order:
            task = settings.tasks[index]
            if any(parent in failed for parent in parents[index]):
                failed.add(index)
                uncompleted += 1
                steps.append(self._failed_step(task, index))
                slots[index] = f"Task {index} failed."
                if settings.stop_on_error:
                    break
                continue
            summary = await self._run_task(task, index, slots, settings)
            if summary is None:
                failed.add(index)
                uncompleted += 1
                steps.append(self._failed_step(task, index))
                slots[index] = f"Task {index} failed."
                if settings.stop_on_error:
                    break
                continue
            completed += 1
            slots[index] = summary[0]
            steps.append(self._completed_step(task, index, summary[0], summary[1]))
        self._progress(Progress.COMPLETE)
        return self._result(admission_id, completed, uncompleted, steps)

    def _topological_order(self, count: int, edges: tuple[tuple[int, int], ...]) -> tuple[int, ...]:
        # Orders tasks so parents run first, breaking ties by smallest index.
        children: dict[int, list[int]] = {index: [] for index in range(count)}
        pending: dict[int, int] = {index: 0 for index in range(count)}
        for child, parent in edges:
            children[parent].append(child)
            pending[child] += 1
        ready = sorted(index for index in range(count) if pending[index] == 0)
        order: list[int] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in children[current]:
                pending[child] -= 1
                if pending[child] == 0:
                    ready.append(child)
            ready.sort()
        if len(order) != count:
            raise TaskBoardDependencyInvalid()
        return tuple(order)

    def _dag_parents(self, settings: TaskBoardSettings) -> dict[int, tuple[int, ...]]:
        # Maps each task to its sorted direct parents for context selection.
        grouped: dict[int, list[int]] = {index: [] for index in range(len(settings.tasks))}
        for child, parent in settings.dependencies:
            grouped[child].append(parent)
        return {index: tuple(sorted(parents)) for index, parents in grouped.items()}

    async def _run_task(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> tuple[str, str] | None:
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
                return (summary, thread)
            except Exception:
                # Attempt failures stay local: stop-on-error is the caller's policy.
                continue
        return None

    def _build_prompt(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> str:
        # An isolated board hands its agents no prior-results channel at all; a windowed board
        # renders exactly the trailing slice the window admits and nothing older.
        if settings.context_mode is TaskBoardContextMode.ISOLATED:
            return self._summarizer.render_prompt(task, index, None)
        if settings.execution_type is TaskBoardExecutionType.DAG:
            return self._build_dag_prompt(task, index, summaries, settings)
        windowed = self._summarizer.windowed(summaries, index, settings.window)
        context = self._summarizer.render_context(windowed)
        return self._summarizer.render_prompt(task, index, context)

    def _build_dag_prompt(
        self, task: str, index: int, summaries: list[str], settings: TaskBoardSettings
    ) -> str:
        # Renders only direct dependencies' summaries so unrelated context never leaks in.
        parents = self._dag_parents(settings)[index]
        selected = tuple((parent, summaries[parent]) for parent in parents if summaries[parent])
        context = self._summarizer.render_context(selected)
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
