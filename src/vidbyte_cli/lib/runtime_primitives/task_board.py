"""Sequential task-board execution over separate Codex agents with checkpointed handoffs.

The board owns ordering, context, and durability. The SDK owns each task turn. Raw prior
results never reach the next agent unless the handoff mode asks for them; a windowed board
forwards bounded entries and an isolated board forwards nothing at all. Every finished step
is durably recorded before the next one starts, so a crash costs at most one step.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import (
    TaskBoardCheckpoint,
    TaskBoardCheckpointMode,
    TaskBoardContextMode,
    TaskBoardHandoffMode,
    TaskBoardPrefix,
    TaskBoardResult,
    TaskBoardRunControls,
    TaskBoardSettings,
    TaskBoardStepResult,
    TaskBoardTurn,
)
from ..constants.runtime import TaskBoardCodexConfig, TaskBoardLimit
from ..constants.runtime import TaskBoardProgress as Progress
from ..errors.cli_error import CliError
from ..errors.failures import (
    LocalFileWriteFailed,
    TaskBoardCheckpointMismatch,
    TaskBoardHostFailed,
)
from .task_board_checkpoints import TaskBoardCheckpointer

if TYPE_CHECKING:
    from vidbyte.agents.codex import CodexHarnessAgent
    from vidbyte.agents.types import AgentMessage


class TaskBoardSummarizer:
    """Builds bounded summaries, handoff entries, and per-task prompts without network calls."""

    def summarize(self, text: str, mode: str, limit: int) -> str:
        # Shrinks one result deterministically so prompts stay bounded.
        cleaned = text.strip()
        if len(cleaned) <= limit:
            return cleaned
        if mode == "head-tail":
            return self._head_tail(cleaned, limit)
        return self._truncate_tail(cleaned, limit)

    def handoff(self, settings: TaskBoardSettings, task: str, summary: str, result: str) -> str:
        # One entry per finished task, shaped once at write time so every later reader — a
        # live step, a resumed step, and a replay — sees byte-identical prior context.
        if settings.handoff_mode is TaskBoardHandoffMode.TASK_AND_SUMMARY:
            return f"Task: {task.strip()}\nResult: {summary}"
        if settings.handoff_mode is TaskBoardHandoffMode.FULL_RESULT:
            body = result.strip() or summary
            return self.summarize(body, "truncate-tail", TaskBoardLimit.MAX_TASK_CHARS)
        return summary

    def render_context(self, entries: tuple[tuple[int, str], ...]) -> str:
        # Labels each prior entry so agents cannot confuse board order.
        return "\n".join(f"[{index}] {entry}" for index, entry in entries)

    def render_prompt(self, task: str, index: int, context: str | None) -> str:
        # A None context is an isolated board: the prior-results section is absent, not
        # merely empty, so no agent can infer that earlier work exists to be reconciled.
        if context is None:
            return f"Task {index}: {task}\n\nComplete only this task."
        prior = context if context.strip() else "(no prior results)"
        return f"Task {index}: {task}\n\nPrior summaries:\n{prior}\n\nComplete only this task."

    def windowed(
        self, entries: list[str | None], index: int, window: int
    ) -> tuple[tuple[int, str], ...]:
        # Slices the trailing window so task N sees exactly N-window..N-1. Unfilled positions
        # are skipped rather than closed up, so a sparse board keeps its real board indices.
        start = max(0, index - window)
        sliced = ((start + offset, entries[start + offset]) for offset in range(index - start))
        return tuple((position, entry) for position, entry in sliced if entry is not None)

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
    """One board invocation's environment, per-task SDK agents, and checkpoint policy."""

    def __init__(
        self,
        environment: Mapping[str, str],
        progress: Callable[[str], None],
        stream: Callable[[TaskBoardCheckpoint], None] | None = None,
    ) -> None:
        # Stores env, progress, and the optional per-step stream without starting any turn.
        self._environment = dict(environment)
        self._progress = progress
        self._stream = stream
        self._executable = ""
        self._working_directory = ""
        self._summarizer = TaskBoardSummarizer()
        self._checkpointer: TaskBoardCheckpointer | None = None
        self._controls = TaskBoardRunControls()

    def with_checkpoints(
        self, checkpointer: TaskBoardCheckpointer, controls: TaskBoardRunControls
    ) -> None:
        # Arms durability plus every resume, replay, slicing, and budget bound in one object,
        # so the session never carries a half-configured mix of run controls.
        self._checkpointer = checkpointer
        self._controls = controls

    def prepare(self, plan: Plan) -> None:
        # Loads the SDK and records paths without starting a paid model turn.
        from vidbyte.agents.codex import CodexHarnessAgent  # noqa: F401

        self._executable = str(plan.executable)
        self._working_directory = str(plan.working_directory)

    def run(self, plan: Plan, settings: TaskBoardSettings, admission_id: str) -> TaskBoardResult:
        # Runs the ordered board synchronously for command-layer callers.
        try:
            if self._controls.replay_index is not None:
                index = self._controls.replay_index
                return asyncio.run(self._replay(settings, admission_id, index))
            return asyncio.run(self._run(plan, settings, admission_id))
        except TaskBoardHostFailed:
            raise
        except (TimeoutError, RuntimeError) as error:
            raise TaskBoardHostFailed() from error

    def preview_prompt(self, settings: TaskBoardSettings, index: int) -> str:
        # Rebuilds one step's exact prompt from stored entries without starting an agent, so a
        # window or handoff mistake is caught before a caller pays for the turn that shows it.
        checkpointer = self._require_checkpointer()
        if index >= len(settings.tasks):
            raise TaskBoardCheckpointMismatch("replay-past-end")
        checkpointer.validate_manifest(settings)
        entries = self._empty_entries(settings)
        self._seed(entries, [], checkpointer.load_prefix(index), settings)
        return self._build_prompt(settings.tasks[index], index, entries, settings)

    async def _run(
        self, plan: Plan, settings: TaskBoardSettings, admission_id: str
    ) -> TaskBoardResult:
        # Runs the selected indices in board order, each in a fresh agent, recording every
        # attempted step before the next one starts so board indices and the window stay aligned.
        del plan
        entries = self._empty_entries(settings)
        steps: list[TaskBoardStepResult] = []
        self._progress(Progress.TASK_STARTING)
        prefix = self._load_prefix(entries, steps, settings)
        completed, failed = prefix.completed, prefix.failed
        # `spent` is this invocation's usage and is what the budget guard reads, because a
        # resumed board would otherwise halt on the spend its earlier invocations already
        # made. `tokens` stays board-cumulative, since that is what the result reports.
        tokens, spent, started = prefix.total_tokens, 0, 0
        stopped: str | None = None
        for index in self._indices(prefix, settings):
            if stopped := self._halt_reason(started, spent):
                break
            started += 1
            turn = await self._run_task(settings.tasks[index], index, entries, settings)
            spent += 0 if turn is None else (turn.total_tokens or 0)
            tokens += 0 if turn is None else (turn.total_tokens or 0)
            step = self._step_of(settings.tasks[index], index, turn)
            self._record(step, turn, entries, settings, admission_id, tokens)
            steps.append(step)
            completed, failed = completed + int(turn is not None), failed + int(turn is None)
            if turn is None and settings.stop_on_error:
                stopped = "stop-on-error"
                break
        self._progress(Progress.COMPLETE)
        return self._result(settings, admission_id, completed, failed, steps, tokens, stopped)

    async def _replay(
        self, settings: TaskBoardSettings, admission_id: str, index: int
    ) -> TaskBoardResult:
        # Rebuilds one step's exact prompt from stored entries and runs only that step, so a
        # flaky step can be chased repeatedly without disturbing anything else on the board.
        checkpointer = self._require_checkpointer()
        if index >= len(settings.tasks):
            raise TaskBoardCheckpointMismatch("replay-past-end")
        checkpointer.validate_manifest(settings)
        entries = self._empty_entries(settings)
        self._progress(Progress.TASK_STARTING)
        self._seed(entries, [], checkpointer.load_prefix(index), settings)
        turn = await self._run_task(settings.tasks[index], index, entries, settings)
        step = self._step_of(settings.tasks[index], index, turn)
        tokens = 0 if turn is None else (turn.total_tokens or 0)
        self._record(step, turn, entries, settings, admission_id, tokens)
        self._progress(Progress.COMPLETE)
        return self._result(
            settings, admission_id, int(turn is not None), int(turn is None), [step], tokens, None
        )

    def _load_prefix(
        self,
        entries: list[str | None],
        steps: list[TaskBoardStepResult],
        settings: TaskBoardSettings,
    ) -> TaskBoardPrefix:
        # Seeds the window and the result list from stored steps; a fresh run only stamps the
        # manifest, which is what makes this board addressable by id from then on.
        if self._checkpointer is None:
            return TaskBoardPrefix(start_index=0, completed=0, failed=0, total_tokens=0)
        if self._controls.start_from > len(settings.tasks):
            raise TaskBoardCheckpointMismatch("resume-past-end")
        if self._controls.start_from == 0 and not self._controls.retry_failed_only:
            self._stamp_manifest(settings)
            return TaskBoardPrefix(start_index=0, completed=0, failed=0, total_tokens=0)
        self._checkpointer.validate_manifest(settings)
        if self._controls.retry_failed_only:
            return self._repair_prefix(entries, steps, settings)
        stored = self._checkpointer.load_prefix(self._controls.start_from)
        self._seed(entries, steps, stored, settings)
        return TaskBoardPrefix(
            start_index=len(stored),
            completed=sum(1 for record in stored if record.status == "completed"),
            failed=sum(1 for record in stored if record.status == "failed"),
            total_tokens=sum(record.total_tokens or 0 for record in stored),
        )

    def _repair_prefix(
        self,
        entries: list[str | None],
        steps: list[TaskBoardStepResult],
        settings: TaskBoardSettings,
    ) -> TaskBoardPrefix:
        # A repair pass re-runs only the stored failures, so a board with 97 successes and 3
        # failures costs three turns rather than paying again for work that already landed.
        checkpointer = self._require_checkpointer()
        stored = checkpointer.load_stored(len(settings.tasks))
        failures = tuple(
            record.index
            for record in stored
            if record.status == "failed" and record.index >= self._controls.start_from
        )
        # A failure about to be re-run seeds its window entry but contributes no step record
        # and no failed count, because the loop is about to produce both for that same index.
        self._seed(entries, steps, stored, settings, skip=frozenset(failures))
        return TaskBoardPrefix(
            start_index=self._controls.start_from,
            completed=sum(1 for record in stored if record.status == "completed"),
            failed=sum(1 for record in stored if record.status == "failed") - len(failures),
            total_tokens=sum(record.total_tokens or 0 for record in stored),
            replay_indices=failures,
        )

    def _indices(self, prefix: TaskBoardPrefix, settings: TaskBoardSettings) -> tuple[int, ...]:
        # The exact board positions this invocation will attempt, in board order.
        if self._controls.retry_failed_only:
            return prefix.replay_indices
        return tuple(range(prefix.start_index, len(settings.tasks)))

    def _halt_reason(self, started: int, tokens: int) -> str | None:
        # Budgets and slicing are checked between steps, so at most one step can overshoot a
        # limit and the caller always gets a resume command instead of a truncated board.
        if self._controls.stop_after is not None and started >= self._controls.stop_after:
            return "stop-after"
        return self._controls.exhausted(tokens)

    def _seed(
        self,
        entries: list[str | None],
        steps: list[TaskBoardStepResult],
        stored: tuple[TaskBoardCheckpoint, ...],
        settings: TaskBoardSettings,
        skip: frozenset[int] = frozenset(),
    ) -> None:
        # Replays stored records into this run's context, rebuilding each handoff entry from
        # the stored task and result so a resumed prompt matches what a fresh run would build.
        for record in stored:
            entries[record.index] = self._summarizer.handoff(
                settings, record.task, record.summary, record.result_text
            )
            if record.index in skip:
                continue
            steps.append(
                TaskBoardStepResult(
                    index=record.index,
                    task=record.task,
                    summary=record.summary,
                    status=record.status,
                    thread_id=record.thread_id,
                )
            )

    def _record(
        self,
        step: TaskBoardStepResult,
        turn: TaskBoardTurn | None,
        entries: list[str | None],
        settings: TaskBoardSettings,
        admission_id: str,
        tokens: int,
    ) -> None:
        # Fills this step's handoff entry, then applies the checkpoint policy. Order matters:
        # the entry has to exist before the next task builds its prompt, and the checkpoint has
        # to be written before the next task starts, or a crash loses a step that really ran.
        del tokens
        result = "" if turn is None else turn.result_text
        entries[step.index] = self._summarizer.handoff(settings, step.task, step.summary, result)
        if self._checkpointer is None:
            return
        fallback = self._build_prompt(step.task, step.index, entries, settings)
        prompt = turn.prompt if turn else fallback
        record = TaskBoardCheckpoint(
            board_id=self._checkpointer.board_id,
            index=step.index,
            parent_index=self._parent_index(entries, step.index),
            task=step.task,
            prompt=prompt,
            summary=step.summary,
            result_text=result,
            status=step.status,
            thread_id=step.thread_id,
            total_tokens=None if turn is None else turn.total_tokens,
            estimated_cost_usd=self._step_cost(turn),
            admission_id=admission_id,
            created_at=TaskBoardCheckpointer.timestamp(),
        )
        self._persist(record)

    def _persist(self, record: TaskBoardCheckpoint) -> None:
        # Checkpointing never fails a step: a write error is reported on stderr and the board
        # keeps its progress, because losing a paid turn to a full disk is the worse outcome.
        checkpointer = self._require_checkpointer()
        try:
            step_file = checkpointer.write_step(record)
        except LocalFileWriteFailed:
            self._progress(f"Checkpoint write failed for task {record.index}; continuing.")
            return
        if self._controls.checkpoint_mode is TaskBoardCheckpointMode.STREAM and self._stream:
            self._stream(record)
        if self._controls.checkpoint_mode is TaskBoardCheckpointMode.EXPORT:
            self._append_export(checkpointer, record)
        if self._controls.on_checkpoint and not checkpointer.run_hook(
            self._controls.on_checkpoint, record, step_file
        ):
            self._progress(f"Checkpoint hook failed for task {record.index}; continuing.")

    def _append_export(
        self, checkpointer: TaskBoardCheckpointer, record: TaskBoardCheckpoint
    ) -> None:
        # The export log is an observer of the same event, so its failure is also non-fatal.
        try:
            checkpointer.append_export(record, checkpointer.export_path(self._controls.export_file))
        except (LocalFileWriteFailed, OSError):
            # OSError: resolving a configured export path can fail before the store is reached.
            self._progress(f"Checkpoint export failed for task {record.index}; continuing.")

    def _parent_index(self, entries: list[str | None], index: int) -> int | None:
        # The nearest filled position below this one: the step this step's prompt actually read.
        below = [position for position in range(index) if entries[position] is not None]
        return below[-1] if below else None

    def _step_cost(self, turn: TaskBoardTurn | None) -> float | None:
        # Unknown usage stays None rather than 0.0, so a budget never treats it as free.
        if turn is None or turn.total_tokens is None:
            return None
        return self._controls.cost_of(turn.total_tokens)

    def _stamp_manifest(self, settings: TaskBoardSettings) -> None:
        # A board that cannot record its manifest is still worth running; only resume is lost.
        try:
            self._require_checkpointer().write_manifest(settings)
        except LocalFileWriteFailed:
            self._progress("Checkpoint manifest write failed; continuing.")

    def _require_checkpointer(self) -> TaskBoardCheckpointer:
        # Resume, replay, preview, and repair are unreachable without one; the command arms it.
        if self._checkpointer is None:
            raise RuntimeError("task board checkpoint operation requested without a checkpointer")
        return self._checkpointer

    @staticmethod
    def _empty_entries(settings: TaskBoardSettings) -> list[str | None]:
        # One slot per board position, so a sparse board keeps its real indices.
        return [None] * len(settings.tasks)

    async def _run_task(
        self, task: str, index: int, entries: list[str | None], settings: TaskBoardSettings
    ) -> TaskBoardTurn | None:
        # One task start to finish. Every attempt builds its own agent and renders the same
        # prompt, so a retry recovers from a dead host rather than re-deciding the context.
        for attempt in range(settings.max_retries_per_task + 1):
            if attempt > 0:
                self._progress(Progress.TASK_RETRYING)
            try:
                prompt = self._build_prompt(task, index, entries, settings)
                reply = await self._turn(self._build_agent(index, settings), prompt, settings)
                result = self._completed_text(reply)
                return TaskBoardTurn(
                    prompt=prompt,
                    summary=self._summarizer.summarize(
                        result, settings.summary_mode.value, settings.summary_max_chars
                    ),
                    result_text=result,
                    thread_id=self._thread_id(reply),
                    total_tokens=self._usage_of(reply),
                )
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
        self, task: str, index: int, entries: list[str | None], settings: TaskBoardSettings
    ) -> str:
        # An isolated board hands its agents no prior-results channel at all; a windowed board
        # renders exactly the trailing slice the window admits and nothing older.
        if settings.context_mode is TaskBoardContextMode.ISOLATED:
            return self._summarizer.render_prompt(task, index, None)
        windowed = self._summarizer.windowed(entries, index, settings.window)
        context = self._summarizer.render_context(windowed)
        return self._summarizer.render_prompt(task, index, context)

    def _build_agent(self, index: int, settings: TaskBoardSettings) -> CodexHarnessAgent:
        # Constructs a fresh agent so threads never leak across tasks. The client config is
        # built here rather than in a helper because its type only exists under this import.
        from vidbyte.agents.codex import CodexHarnessAgent
        from vidbyte.lib.dataclasses.codex import (
            CodexAgentSettings,
            CodexClientSettings,
            CodexHarnessAgentSettings,
            CodexThreadSettings,
            CodexTurnSettings,
        )
        from vidbyte.lib.enums.codex import CodexReasoningEffort, CodexSandbox

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
                    client=client,
                    thread=CodexThreadSettings(
                        model=settings.agent.model,
                        sandbox=CodexSandbox(settings.agent.sandbox.value),
                    ),
                    turn=CodexTurnSettings(
                        effort=CodexReasoningEffort(settings.agent.reasoning_effort.value)
                    ),
                ),
            )
        )

    async def _turn(
        self, agent: CodexHarnessAgent, prompt: str, settings: TaskBoardSettings
    ) -> AgentMessage:
        # Cancels slow turns so the SDK client unwinds before continuing.
        from vidbyte.lib.dataclasses.codex import CodexRunInput

        try:
            async with asyncio.timeout(settings.agent.turn_timeout_seconds):
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

    def _step_of(self, task: str, index: int, turn: TaskBoardTurn | None) -> TaskBoardStepResult:
        # One shape for both outcomes; a failure keeps a placeholder summary so board indices
        # and the window slice stay aligned with what a fully successful run would have built.
        if turn is None:
            return TaskBoardStepResult(
                index=index,
                task=task,
                summary=f"Task {index} failed.",
                status="failed",
                thread_id=f"task-board-{index}-failed",
            )
        return TaskBoardStepResult(
            index=index,
            task=task,
            summary=turn.summary,
            status="completed",
            thread_id=turn.thread_id,
        )

    def _result(
        self,
        settings: TaskBoardSettings,
        admission_id: str,
        completed: int,
        failed: int,
        steps: list[TaskBoardStepResult],
        tokens: int,
        stopped: str | None,
    ) -> TaskBoardResult:
        # Joins step summaries into the board-level text and names where the board lives, so a
        # calling agent can address it later by absolute path rather than by remembering a run.
        ordered = sorted(steps, key=lambda step: step.index)
        text = "\n".join(f"[{step.index}] {step.summary}" for step in ordered)
        checkpointer = self._checkpointer
        return TaskBoardResult(
            admission_id=admission_id,
            completed=completed,
            failed=failed,
            steps=tuple(ordered),
            board_id=None if checkpointer is None else checkpointer.board_id,
            board_dir=None if checkpointer is None else str(checkpointer.directory),
            export_file=self._result_export(checkpointer),
            report_file=self._write_report(checkpointer),
            resume_command=self._resume_command(checkpointer, settings, ordered),
            total_tokens=tokens or None,
            estimated_cost_usd=self._controls.cost_of(tokens) if tokens else None,
            stopped_reason=stopped,
            text=text,
        )

    def _result_export(self, checkpointer: TaskBoardCheckpointer | None) -> str | None:
        # Only an export-mode run has a log to point at; other modes report nothing here.
        exporting = self._controls.checkpoint_mode is TaskBoardCheckpointMode.EXPORT
        if checkpointer is None or not exporting:
            return None
        return str(checkpointer.export_path(self._controls.export_file))

    def _write_report(self, checkpointer: TaskBoardCheckpointer | None) -> str | None:
        # The report is written last, from the same stored chain `status` reads, so the file
        # a human opens and the record an agent queries can never describe different runs.
        # Reading that chain can itself fail when the manifest write failed earlier, and a
        # report is never worth failing a board whose paid work already finished.
        if checkpointer is None or not self._controls.report_file:
            return None
        try:
            report = Path(self._controls.report_file)
            return str(checkpointer.write_report(checkpointer.chain(), report))
        except (LocalFileWriteFailed, OSError):
            # OSError: resolving the configured report path can fail before the store is reached.
            self._progress("Checkpoint report write failed; continuing.")
            return None
        except CliError:
            self._progress("Checkpoint report could not read the board; continuing.")
            return None

    def _resume_command(
        self,
        checkpointer: TaskBoardCheckpointer | None,
        settings: TaskBoardSettings,
        steps: list[TaskBoardStepResult],
    ) -> str | None:
        # A ready-to-paste continuation, so a caller never reconstructs flags from help text.
        # It points at the first step that did not complete, which after a stop-on-error halt
        # is the failure itself rather than the step after it, and is omitted only when the
        # whole board finished.
        if checkpointer is None or not steps:
            return None
        done = {step.index for step in steps if step.status == "completed"}
        if any(step.status == "failed" for step in steps):
            return checkpointer.resume_command(0, repair=True)
        following = next(
            (index for index in range(len(settings.tasks)) if index not in done),
            len(settings.tasks),
        )
        if following >= len(settings.tasks):
            return None
        return checkpointer.resume_command(following)

    def _prompt(self) -> str:
        # Loads the fixed stage prompt for every board task agent.
        return files(__package__).joinpath("task_board_system.md").read_text(encoding="utf-8")
