"""Task-board execution over separate Codex agents with checkpointed handoffs.

The board owns ordering, context, and durability. The SDK owns each task turn. Raw prior
results never reach the next agent unless the handoff mode asks for them; a linear board
forwards windowed entries, a DAG board forwards only its direct dependencies' entries, and an
isolated board forwards nothing at all. Every finished step is durably recorded before the
next one starts, so a crash costs at most one step.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from importlib.resources import files
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import (
    TaskBoardCheckpoint,
    TaskBoardCheckpointMode,
    TaskBoardContextMode,
    TaskBoardExecutionType,
    TaskBoardHandoffMode,
    TaskBoardPrefix,
    TaskBoardResult,
    TaskBoardRunControls,
    TaskBoardSettings,
    TaskBoardStepResult,
    TaskBoardTaskOutcome,
    TaskBoardTurn,
)
from ..constants.runtime import TaskBoardCodexConfig, TaskBoardLimit
from ..constants.runtime import TaskBoardProgress as Progress
from ..errors.cli_error import CliError
from ..errors.failures import (
    LocalFileWriteFailed,
    TaskBoardCheckpointMismatch,
    TaskBoardDependencyInvalid,
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

    def render_decompose_prompt(self, task: str, index: int, max_subtasks: int) -> str:
        # Names the native tool without putting control syntax into the final text channel.
        return (
            f"Task {index}: {task}\n\nComplete only this task. You see only this task. "
            "If splitting it improves execution, call the provided decompose_tool with "
            f"2 to {max_subtasks} ordered, self-contained subtasks. Otherwise complete the "
            "task normally."
        )

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


_DECOMPOSE_TOOL_DESCRIPTION = (
    "Replace the current board task with a short ordered list of self-contained subtasks that "
    "run in its place, one after another, before any later task on the board starts. "
    "Call this tool only when the current task is genuinely better handled as separate steps, "
    "for example when it bundles independent deliverables or needs one step's output before "
    "the next can begin; if the task is small or already a single coherent change, do not "
    "call it and complete the task yourself. "
    "Pass at least two distinct subtasks and no more than the maximum named in your task "
    "prompt; blank entries, entries over 20,000 characters, and case-insensitive duplicates "
    "are dropped, and anything past the maximum is ignored, so a call left with fewer than two "
    "valid subtasks is rejected and the task stays whole. "
    "Only the first accepted call in this turn counts, so a second call cannot revise the "
    "split; decide on the full list before calling. "
    "Each child runs later in a fresh agent that sees only its own subtask string, with no "
    "access to this conversation, the parent task, its siblings, or any prior results, and "
    "that child cannot decompose again. "
    "Write every subtask as a complete instruction that names the files, constraints, and "
    "acceptance criteria it needs, because anything left implicit is lost. "
    "After a call is accepted, end your turn with a brief final message describing the split "
    "instead of doing the subtasks' work yourself, since the children will do it."
)
_DECOMPOSE_SUBTASKS_DESCRIPTION = (
    "The ordered list of child task statements that replaces the current task at its board "
    "position, where the first string runs first and the last runs last. "
    "Provide between two and the maximum number of subtasks named in your task prompt, each "
    "a distinct, non-blank instruction under 20,000 characters. "
    "Every string is handed verbatim to a fresh isolated agent that has never seen the parent "
    "task, its siblings, or any earlier board results, so each must restate the goal, the "
    "relevant files or inputs, the constraints, and what done looks like. "
    "Order the list so that any subtask relying on another's changes comes after it, because "
    "children run strictly in list order and nothing passes between them except the files "
    "they change. "
    "Entries are stripped of surrounding whitespace, case-insensitive duplicates keep only "
    "their first occurrence, and entries past the maximum are discarded rather than rejected. "
    "Do not include numbering, bullet markers, or commentary about the split itself, since "
    "each string becomes a task prompt exactly as written."
)


class TaskBoardDecomposeCapture:
    """Captures one parent attempt's accepted native decomposition call."""

    def __init__(self, max_subtasks: int) -> None:
        # Keeps the attempt-local bound and prevents concurrent tool calls from overwriting it.
        self._max_subtasks = max_subtasks
        self._accepted: tuple[str, ...] = ()
        self._lock = Lock()

    @property
    def accepted_subtasks(self) -> tuple[str, ...]:
        # Returns an immutable snapshot for the session's post-turn splice decision.
        with self._lock:
            return self._accepted

    def build_tool(self) -> Any:
        # Uses the SDK's public decorator lazily so command help never starts Codex machinery.
        from vidbyte.tools import tool

        def decompose_tool(
            subtasks: Annotated[
                list[str],
                Field(description=_DECOMPOSE_SUBTASKS_DESCRIPTION),
            ],
        ) -> str:
            # Routes the model's structured call into this attempt's policy-bound capture.
            return self._accept(subtasks)

        # The pinned SDK's tool() takes name and description only in its decorator form.
        return tool(name="decompose_tool", description=_DECOMPOSE_TOOL_DESCRIPTION)(decompose_tool)

    def _accept(self, candidates: list[str]) -> str:
        # Normalizes candidates before the first accepted call becomes immutable.
        cleaned = self._clean_candidates(candidates)
        if len(cleaned) < int(TaskBoardLimit.MIN_SUBTASKS):
            return "No decomposition accepted; provide at least two distinct valid subtasks."
        with self._lock:
            if self._accepted:
                return "A decomposition was already accepted for this task attempt."
            self._accepted = cleaned
        return f"Accepted {len(cleaned)} subtasks for isolated execution."

    def _clean_candidates(self, candidates: list[str]) -> tuple[str, ...]:
        # Drops unsafe entries, preserves first occurrence order, and enforces the local cap.
        seen: set[str] = set()
        kept: list[str] = []
        for candidate in candidates:
            cleaned = candidate.strip()
            if not cleaned or len(cleaned) > int(TaskBoardLimit.MAX_TASK_CHARS):
                continue
            folded = cleaned.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            kept.append(cleaned)
            if len(kept) >= self._max_subtasks:
                break
        return tuple(kept)


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
        order = self._order(settings)
        entries = self._empty_entries(settings)
        self._seed(entries, [], checkpointer.load_prefix(order.index(index), order), settings)
        return self._build_prompt(settings.tasks[index], index, entries, settings)

    async def _run(
        self, plan: Plan, settings: TaskBoardSettings, admission_id: str
    ) -> TaskBoardResult:
        # Runs the selected indices in execution order, each in a fresh agent, recording every
        # attempted step before the next one starts so board indices and handoff entries stay
        # aligned. A linear board runs in board order; a DAG board runs parents first, and a
        # task whose dependency failed is recorded failed without ever starting an agent.
        del plan
        if settings.allow_decompose:
            return await self._run_decomposing(settings, admission_id)
        order = self._order(settings)
        dag = settings.execution_type is TaskBoardExecutionType.DAG
        parents = self._dag_parents(settings)
        entries = self._empty_entries(settings)
        steps: list[TaskBoardStepResult] = []
        self._progress(Progress.TASK_STARTING)
        if dag:
            self._progress(Progress.DAG_PLAN_READY)
        prefix = self._load_prefix(entries, steps, settings, order)
        completed, failed = prefix.completed, prefix.failed
        # A stored failure blocks its dependents exactly like a failure in this invocation.
        blocked = {step.index for step in steps if step.status == "failed"}
        # `spent` is this invocation's usage and is what the budget guard reads, because a
        # resumed board would otherwise halt on the spend its earlier invocations already
        # made. `tokens` stays board-cumulative, since that is what the result reports.
        tokens, spent, started = prefix.total_tokens, 0, 0
        stopped: str | None = None
        for index in self._indices(prefix, order):
            if stopped := self._halt_reason(started, spent):
                break
            blockers = sorted(parent for parent in parents[index] if parent in blocked)
            if dag and blockers:
                # A skip starts no agent, so it neither costs nor counts toward --stop-after.
                turn, note = None, self._skip_detail(blockers)
                self._progress(Progress.TASK_SKIPPED)
            else:
                started += 1
                outcome = await self._run_task(settings.tasks[index], index, entries, settings)
                turn, note = outcome.turn, outcome.note
                if turn is None and dag:
                    self._progress(Progress.TASK_FAILED)
            used = 0 if turn is None else (turn.total_tokens or 0)
            spent, tokens = spent + used, tokens + used
            # Only a DAG failure carries its note: the linear placeholder is what windowed
            # prompts read, so it keeps its exact wording.
            step = self._step_of(settings.tasks[index], index, turn, note if dag else "")
            self._record(step, turn, entries, settings, admission_id, order)
            steps.append(step)
            if turn is None:
                blocked.add(index)
            completed, failed = completed + int(turn is not None), failed + int(turn is None)
            if turn is None and settings.stop_on_error:
                stopped = "stop-on-error"
                break
        self._progress(Progress.COMPLETE)
        return self._result(settings, admission_id, completed, failed, steps, tokens, stopped)

    async def _run_decomposing(
        self, settings: TaskBoardSettings, admission_id: str
    ) -> TaskBoardResult:
        # Replaces eligible parents in a mutable linear board while preserving execution order.
        # This loop exists apart from `_run` because a splice changes the board's length while
        # it runs: `_run` iterates a precomputed execution order and seeds handoff entries by
        # board index, and both assumptions break the moment one task becomes several.
        # `work` is the live board and `depths` runs parallel to it, so the two lists must be
        # spliced together or a child would inherit the wrong decompose eligibility. Every
        # original task starts at depth zero, meaning it may still decompose.
        work = list(settings.tasks)
        depths = [0] * len(work)
        steps: list[TaskBoardStepResult] = []
        # Counters are local to this invocation because the command rejects checkpointing for
        # a decomposing board, so there is no stored prefix to resume from or add to.
        completed, failed, tokens = 0, 0, 0
        stopped: str | None = None
        self._progress(Progress.TASK_STARTING)
        # A `while` over a manual index rather than a `for` over the list, because a splice
        # must re-read `len(work)` and must be able to leave `index` where it is.
        index = 0
        while index < len(work):
            task = work[index]
            # The limit is recomputed per task from the live board size, so a late parent on a
            # board that has already grown near the 500-task ceiling gets a smaller cap, and
            # `None` withholds the tool entirely for children and for a board with no room.
            decompose_limit = self._decompose_limit(len(work), depths[index], settings)
            # Every task runs isolated with an empty entry list: a splice shifts board indices,
            # so windowed or dependency context would point at the wrong earlier results.
            outcome = await self._run_task(
                task,
                index,
                [],
                settings,
                isolated=True,
                decompose_max_subtasks=decompose_limit,
            )
            turn = outcome.turn
            if turn is None:
                # A failed parent never splices, even if its tool call was accepted before the
                # turn died: the capture is attempt-local, and only a completed turn returns it.
                failed += 1
                steps.append(self._step_of(task, index, None))
                if settings.stop_on_error:
                    stopped = "stop-on-error"
                    break
                index += 1
                continue
            # A completed parent counts as completed and pays its tokens whether or not it
            # decomposed, because its turn ran to the end either way and was billed for.
            completed += 1
            tokens += turn.total_tokens or 0
            children = outcome.subtasks
            # The capture already rejects a call with fewer than two valid subtasks, so this
            # threshold is a second guard that keeps a one-child "split" from ever replacing a
            # task with a copy of itself.
            if len(children) >= int(TaskBoardLimit.MIN_SUBTASKS):
                # The children take the parent's slot in place, so every later task shifts right
                # by `len(children) - 1` and still runs after all of them. Depth one marks each
                # child ineligible, which is what keeps decomposition to a single level.
                work[index : index + 1] = list(children)
                depths[index : index + 1] = [1] * len(children)
                steps.append(self._decomposed_step(task, index, len(children), turn.thread_id))
                # `index` is deliberately not advanced: the first child now sits at this
                # position, so the next iteration runs it rather than skipping past it.
                continue
            # No accepted split means the parent's own final text is the task's result, the
            # same step shape a board without --allow-decompose records.
            steps.append(self._step_of(task, index, turn))
            index += 1
        self._progress(Progress.COMPLETE)
        # `steps` stays in append order because a splice reuses a parent's index for its first
        # child, so the result lists each decomposed parent directly before the children that
        # replaced it.
        return self._result(settings, admission_id, completed, failed, steps, tokens, stopped)

    def _decompose_limit(
        self, current_size: int, depth: int, settings: TaskBoardSettings
    ) -> int | None:
        # Omits the tool for children and for a board with fewer than two available slots.
        capacity = int(TaskBoardLimit.MAX_TASKS) - current_size + 1
        if depth or capacity < int(TaskBoardLimit.MIN_SUBTASKS):
            return None
        return min(settings.max_subtasks, capacity)

    async def _replay(
        self, settings: TaskBoardSettings, admission_id: str, index: int
    ) -> TaskBoardResult:
        # Rebuilds one step's exact prompt from stored entries and runs only that step, so a
        # flaky step can be chased repeatedly without disturbing anything else on the board.
        checkpointer = self._require_checkpointer()
        if index >= len(settings.tasks):
            raise TaskBoardCheckpointMismatch("replay-past-end")
        checkpointer.validate_manifest(settings)
        order = self._order(settings)
        entries = self._empty_entries(settings)
        self._progress(Progress.TASK_STARTING)
        self._seed(entries, [], checkpointer.load_prefix(order.index(index), order), settings)
        outcome = await self._run_task(settings.tasks[index], index, entries, settings)
        turn, note = outcome.turn, outcome.note
        dag = settings.execution_type is TaskBoardExecutionType.DAG
        step = self._step_of(settings.tasks[index], index, turn, note if dag else "")
        tokens = 0 if turn is None else (turn.total_tokens or 0)
        self._record(step, turn, entries, settings, admission_id, order)
        self._progress(Progress.COMPLETE)
        return self._result(
            settings, admission_id, int(turn is not None), int(turn is None), [step], tokens, None
        )

    def _load_prefix(
        self,
        entries: list[str | None],
        steps: list[TaskBoardStepResult],
        settings: TaskBoardSettings,
        order: tuple[int, ...],
    ) -> TaskBoardPrefix:
        # Seeds the handoff entries and the result list from stored steps; a fresh run only
        # stamps the manifest, which is what makes this board addressable by id from then on.
        # `--from N` counts positions in the execution order, so on a DAG board it skips the
        # first N steps that ran rather than board indices 0 through N-1.
        if self._checkpointer is None:
            return TaskBoardPrefix(start_index=0, completed=0, failed=0, total_tokens=0)
        if self._controls.start_from > len(settings.tasks):
            raise TaskBoardCheckpointMismatch("resume-past-end")
        if self._controls.start_from == 0 and not self._controls.retry_failed_only:
            self._stamp_manifest(settings)
            return TaskBoardPrefix(start_index=0, completed=0, failed=0, total_tokens=0)
        self._checkpointer.validate_manifest(settings)
        if self._controls.retry_failed_only:
            return self._repair_prefix(entries, steps, settings, order)
        stored = self._checkpointer.load_prefix(self._controls.start_from, order)
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
        order: tuple[int, ...],
    ) -> TaskBoardPrefix:
        # A repair pass re-runs only the stored failures, so a board with 97 successes and 3
        # failures costs three turns rather than paying again for work that already landed.
        # Failures re-run in execution order, so on a DAG board a repaired parent runs before
        # the dependent it had blocked, and that dependent then gets a real attempt.
        checkpointer = self._require_checkpointer()
        stored = checkpointer.load_stored(len(settings.tasks))
        failed = {record.index for record in stored if record.status == "failed"}
        failures = tuple(index for index in order[self._controls.start_from :] if index in failed)
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

    def _indices(self, prefix: TaskBoardPrefix, order: tuple[int, ...]) -> tuple[int, ...]:
        # The exact board positions this invocation will attempt, in execution order.
        if self._controls.retry_failed_only:
            return prefix.replay_indices
        return order[prefix.start_index :]

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
        order: tuple[int, ...],
    ) -> None:
        # Fills this step's handoff entry, then applies the checkpoint policy. Order matters:
        # the entry has to exist before the next task builds its prompt, and the checkpoint has
        # to be written before the next task starts, or a crash loses a step that really ran.
        result = "" if turn is None else turn.result_text
        entries[step.index] = self._summarizer.handoff(settings, step.task, step.summary, result)
        if self._checkpointer is None:
            return
        fallback = self._build_prompt(step.task, step.index, entries, settings)
        prompt = turn.prompt if turn else fallback
        record = TaskBoardCheckpoint(
            board_id=self._checkpointer.board_id,
            index=step.index,
            parent_index=self._parent_index(entries, step.index, order),
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

    def _parent_index(
        self, entries: list[str | None], index: int, order: tuple[int, ...]
    ) -> int | None:
        # The nearest filled step before this one in execution order, which links stored steps
        # into the chain a resume walks. On a linear board that is the nearest lower index.
        before = [other for other in order[: order.index(index)] if entries[other] is not None]
        return before[-1] if before else None

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

    @staticmethod
    def _order(settings: TaskBoardSettings) -> tuple[int, ...]:
        # The settings validator already rejects cycles; this guard keeps a model built
        # without validation from silently running nothing.
        order = settings.execution_order()
        if len(order) != len(settings.tasks):
            raise TaskBoardDependencyInvalid()
        return order

    def _dag_parents(self, settings: TaskBoardSettings) -> dict[int, tuple[int, ...]]:
        # Maps each task to its sorted direct parents for context selection and skipping.
        grouped: dict[int, list[int]] = {index: [] for index in range(len(settings.tasks))}
        for child, parent in settings.dependencies:
            grouped[child].append(parent)
        return {index: tuple(sorted(parents)) for index, parents in grouped.items()}

    async def _run_task(
        self,
        task: str,
        index: int,
        entries: list[str | None],
        settings: TaskBoardSettings,
        *,
        isolated: bool = False,
        decompose_max_subtasks: int | None = None,
    ) -> TaskBoardTaskOutcome:
        # One task start to finish. Every attempt builds its own agent and renders the same
        # prompt, so a retry recovers from a dead host rather than re-deciding the context.
        # A failure also returns the note a DAG step records: attempt count, failure kind, and
        # any partial agent text, never task content.
        attempts = settings.max_retries_per_task + 1
        last_note = ""
        for attempt in range(attempts):
            if attempt > 0:
                self._progress(Progress.TASK_RETRYING)
            reply: AgentMessage | None = None
            try:
                capture = (
                    None
                    if decompose_max_subtasks is None
                    else TaskBoardDecomposeCapture(decompose_max_subtasks)
                )
                prompt = self._build_prompt(
                    task,
                    index,
                    entries,
                    settings,
                    isolated=isolated,
                    decompose_max_subtasks=decompose_max_subtasks,
                )
                tool = None if capture is None else capture.build_tool()
                agent = (
                    self._build_agent(index, settings)
                    if tool is None
                    else self._build_agent(index, settings, tool)
                )
                reply = await self._turn(agent, prompt, settings)
                result = self._completed_text(reply)
                turn = TaskBoardTurn(
                    prompt=prompt,
                    summary=self._summarizer.summarize(
                        result, settings.summary_mode.value, settings.summary_max_chars
                    ),
                    result_text=result,
                    thread_id=self._thread_id(reply),
                    total_tokens=self._usage_of(reply),
                )
                subtasks = () if capture is None else capture.accepted_subtasks
                return TaskBoardTaskOutcome(turn=turn, note="", subtasks=subtasks)
            except Exception as error:
                # Attempt failures stay local: stop-on-error is the caller's policy, and
                # only the final note survives so earlier attempts never leak stale causes.
                last_note = self._attempt_note(error, reply, settings, attempt, attempts)
                continue
        return TaskBoardTaskOutcome(
            turn=None,
            note=f"Ran {attempts} attempt(s), all exhausted. {last_note}",
        )

    def _attempt_note(
        self,
        error: Exception,
        reply: AgentMessage | None,
        settings: TaskBoardSettings,
        attempt: int,
        attempts: int,
    ) -> str:
        # Names what ended one attempt so the recorded failure explains itself: timeouts
        # are told apart from dead hosts, and an incomplete turn keeps the partial text
        # its agent left behind, bounded by the same summarizer prompts already use.
        if isinstance(error.__cause__, TimeoutError):
            kind = "the Codex turn timed out before returning"
        elif reply is not None and self._partial_text(reply):
            partial = self._summarizer.summarize(
                self._partial_text(reply),
                settings.summary_mode.value,
                settings.summary_max_chars,
            )
            kind = f"the agent returned an incomplete turn, leaving: {partial}"
        else:
            kind = "the Codex host failed before returning a completed turn"
        return f"Attempt {attempt + 1} of {attempts}: {kind}."

    def _partial_text(self, reply: AgentMessage) -> str:
        # Reads whatever text an incomplete turn left behind without validating it, so a
        # failure note can carry the agent's own words even when the turn never completed.
        try:
            return str(reply.content or "").strip()
        except Exception:
            return ""

    def _skip_detail(self, blockers: list[int]) -> str:
        # Names the failed dependencies so a skip is actionable without re-reading the graph.
        names = ", ".join(f"task {parent}" for parent in blockers)
        return (
            f"No agent was started because {names} did not complete. "
            "Fix or re-run the failed dependencies, then re-run this task."
        )

    def _usage_of(self, reply: AgentMessage) -> int | None:
        # Reads cumulative provider tokens when reported; unknown usage is None, never zero.
        data = reply.codex
        if data is None or not getattr(data, "usage_available", False):
            return None
        total = getattr(data.usage, "total_tokens", None)
        return total if isinstance(total, int) and total >= 0 else None

    def _build_prompt(
        self,
        task: str,
        index: int,
        entries: list[str | None],
        settings: TaskBoardSettings,
        *,
        isolated: bool = False,
        decompose_max_subtasks: int | None = None,
    ) -> str:
        # An isolated board hands its agents no prior-results channel at all; a windowed board
        # renders exactly the trailing slice the window admits and nothing older.
        if decompose_max_subtasks is not None:
            return self._summarizer.render_decompose_prompt(task, index, decompose_max_subtasks)
        if isolated:
            return self._summarizer.render_prompt(task, index, None)
        if settings.context_mode is TaskBoardContextMode.ISOLATED:
            return self._summarizer.render_prompt(task, index, None)
        if settings.execution_type is TaskBoardExecutionType.DAG:
            return self._build_dag_prompt(task, index, entries, settings)
        windowed = self._summarizer.windowed(entries, index, settings.window)
        context = self._summarizer.render_context(windowed)
        return self._summarizer.render_prompt(task, index, context)

    def _build_dag_prompt(
        self, task: str, index: int, entries: list[str | None], settings: TaskBoardSettings
    ) -> str:
        # Renders only direct dependencies' entries so unrelated context never leaks in.
        selected: list[tuple[int, str]] = []
        for parent in self._dag_parents(settings)[index]:
            entry = entries[parent]
            if entry:
                selected.append((parent, entry))
        context = self._summarizer.render_context(tuple(selected))
        return self._summarizer.render_prompt(task, index, context)

    def _build_agent(
        self, index: int, settings: TaskBoardSettings, decompose_tool: Any | None = None
    ) -> CodexHarnessAgent:
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
            experimental_api=True,
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
                tools=() if decompose_tool is None else (decompose_tool,),
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

    def _step_of(
        self, task: str, index: int, turn: TaskBoardTurn | None, detail: str = ""
    ) -> TaskBoardStepResult:
        # One shape for both outcomes; a failure keeps a placeholder summary so board indices
        # and the window slice stay aligned with what a fully successful run would have built.
        # A DAG failure appends its reason: the failed parents, or the final attempt note.
        if turn is None:
            return TaskBoardStepResult(
                index=index,
                task=task,
                summary=f"Task {index} failed. {detail}" if detail else f"Task {index} failed.",
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

    def _decomposed_step(
        self, task: str, index: int, count: int, thread: str
    ) -> TaskBoardStepResult:
        # Records the parent turn that expanded into children at its current position.
        return TaskBoardStepResult(
            index=index,
            task=task,
            summary=f"Task {index} decomposed into {count} subtasks.",
            status="completed",
            thread_id=thread,
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
        # Steps are listed in execution order, which is board order unless the board is a DAG.
        if settings.allow_decompose:
            # Mutable expansion can repeat an index, so append order is the only stable order.
            ordered = list(steps)
        else:
            position = {index: rank for rank, index in enumerate(self._order(settings))}
            ordered = sorted(steps, key=lambda step: position[step.index])
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
        # whole board finished. The point is a position in execution order, as --from reads it.
        if checkpointer is None or not steps:
            return None
        done = {step.index for step in steps if step.status == "completed"}
        if any(step.status == "failed" for step in steps):
            return checkpointer.resume_command(0, repair=True)
        order = self._order(settings)
        following = next(
            (rank for rank, index in enumerate(order) if index not in done), len(order)
        )
        if following >= len(order):
            return None
        return checkpointer.resume_command(following)

    def _prompt(self) -> str:
        # Loads the fixed stage prompt for every board task agent.
        return files(__package__).joinpath("task_board_system.md").read_text(encoding="utf-8")
