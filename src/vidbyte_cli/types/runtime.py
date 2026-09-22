"""Wire and local planning contracts for Vidbyte runtime primitives.

The backend sees only admission metadata; task and machine context stay local. Frozen,
extra-forbid models make contract drift fail before a paid execution can begin.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..lib.constants.runtime import AdmissionReason, StagesLimit


class RuntimeHost(StrEnum):
    """Native coding-agent hosts supported by the first runtime shell."""

    CODEX = "codex"
    CLAUDE = "claude"
    OPENCODE = "opencode"


class RuntimeCapability(BaseModel):
    """One local runtime product published by the backend."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    capability_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)
    execution_location: Literal["local"]
    supported_hosts: tuple[RuntimeHost, ...] = Field(min_length=1)
    admission_price_cents: int = Field(ge=1)


class RuntimeCapabilityCatalog(BaseModel):
    """The runtime-only catalog plus its central wallet funding route."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    capabilities: tuple[RuntimeCapability, ...]
    topup_path: str = Field(pattern=r"^/[^\s]*$")


class RuntimeAdmissionRequest(BaseModel):
    """Safe metadata required to buy one local execution admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    client_runtime_version: Literal["1"] = "1"
    host: RuntimeHost


class RuntimeX402AdmissionRequest(RuntimeAdmissionRequest):
    """Explicit payment opt-in; ordinary wallet requests retain their original wire shape."""

    with_x402_payment: Literal[True] = True


class RuntimeAdmissionGrant(BaseModel):
    """Receipt returned after the backend durably charges admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    admission_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=160)
    execution_location: Literal["local"]
    charged_cents: int = Field(ge=1)
    admitted_at: datetime
    expires_at: datetime | None = None
    grant_token: str | None = Field(default=None, min_length=10, max_length=8192)


class RuntimeHostStatus(BaseModel):
    """Non-secret PATH discovery result for one native coding-agent host."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    host: RuntimeHost
    available: bool
    executable: str | None = None


class RuntimeLaunchPlan(BaseModel):
    """Local-only handoff a future executor will turn into an agent topology."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)
    capability_id: Literal[
        "runtime.review.adversarial-team@1",
        "runtime.adversarial-team@1",
        "runtime.same-host-ensemble@1",
        "runtime.persistence@1",
        "runtime.task-board@1",
        "runtime.stages@1",
    ] = "runtime.review.adversarial-team@1"
    host: RuntimeHost
    executable: Path
    working_directory: Path
    task: str = Field(min_length=1, max_length=20_000)


class TaskBoardSummaryMode(StrEnum):
    """How one prior task result is shrunk before the next agent reads it."""

    TRUNCATE_TAIL = "truncate-tail"
    HEAD_TAIL = "head-tail"


class TaskBoardContextMode(StrEnum):
    """Whether a task agent reads prior task results at all."""

    WINDOWED_SUMMARIES = "windowed-summaries"
    ISOLATED = "isolated"


class TaskBoardHandoffMode(StrEnum):
    """What a finished task hands forward to the tasks allowed to read it."""

    SUMMARY = "summary"
    TASK_AND_SUMMARY = "task-and-summary"
    FULL_RESULT = "full-result"


class TaskBoardCheckpointMode(StrEnum):
    """What happens, beyond the durable save, each time a step is checkpointed."""

    SAVE_ONLY = "save-only"
    STREAM = "stream"
    EXPORT = "export"


class TaskBoardSandbox(StrEnum):
    """Filesystem authority granted to every task agent on one board."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


class TaskBoardReasoningEffort(StrEnum):
    """Reasoning budget requested per task turn; provider-default leaves it unset."""

    PROVIDER_DEFAULT = ""
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class TaskBoardAgentSettings(BaseModel):
    """The Codex agent configuration every iteration of one board is built with."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str = Field(
        default="",
        max_length=100,
        description=(
            "Which Codex model every task agent on this board runs, given as the provider's "
            "own model identifier. Leaving it empty keeps whatever model the installed Codex "
            "host defaults to, which is the right choice when the board is not model-sensitive. "
            "Set it when a board needs a specific capability or price point, because every "
            "iteration of the board is built with the same value and no task can override it. "
            "The model is charged to the caller's own provider account, not to Vidbyte."
        ),
    )
    sandbox: TaskBoardSandbox = Field(
        default=TaskBoardSandbox.WORKSPACE_WRITE,
        description=(
            "How much of the filesystem every task agent on this board may change. "
            "workspace-write, the default, lets a task edit files inside the working directory "
            "and is what a board of implementation tasks needs. read-only lets a task inspect "
            "the tree without writing to it, which is the correct setting for review, audit, "
            "or planning boards. full-access removes the sandbox entirely and should be "
            "reserved for boards whose tasks genuinely have to reach outside the workspace."
        ),
    )
    reasoning_effort: TaskBoardReasoningEffort = Field(
        default=TaskBoardReasoningEffort.PROVIDER_DEFAULT,
        description=(
            "How much reasoning each task turn asks the model to spend before answering. An "
            "empty value leaves the provider default in place, which is what most boards want. "
            "Raising it to high or xhigh suits a board of a few hard tasks, while minimal or "
            "low suits a long board of mechanical ones. Effort multiplies the caller's own "
            "provider bill per task, so a 500-task board at xhigh is a real cost decision."
        ),
    )
    turn_timeout_seconds: int = Field(
        ge=60,
        le=5 * 24 * 60 * 60,
        default=5 * 24 * 60 * 60,
        description=(
            "How long one task turn may run before the board cancels it and counts the attempt "
            "as failed. The default of five days is a ceiling on a wedged child process rather "
            "than a budget any task is expected to approach. Lower it when a board's tasks are "
            "small and a stuck agent should surface quickly instead of blocking the run. The "
            "timeout applies per attempt, so retries each get the full allowance again."
        ),
    )


class TaskBoardRunControls(BaseModel):
    """Where one invocation starts, how far it may go, and what it may spend."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    checkpoint_mode: TaskBoardCheckpointMode = TaskBoardCheckpointMode.SAVE_ONLY
    export_file: str = Field(default="", max_length=4096)
    report_file: str = Field(default="", max_length=4096)
    on_checkpoint: str = Field(default="", max_length=4096)
    start_from: int = Field(ge=0, default=0)
    replay_index: int | None = Field(ge=0, default=None)
    stop_after: int | None = Field(ge=1, default=None)
    retry_failed_only: bool = False
    max_tokens: int | None = Field(ge=1, default=None)
    max_cost_usd: float | None = Field(gt=0, default=None)
    usd_per_million_tokens: float = Field(ge=0, default=10.0)

    def cost_of(self, tokens: int) -> float:
        # One rate for the whole board, so a per-step estimate and the total never disagree.
        return round(tokens / 1_000_000 * self.usd_per_million_tokens, 6)

    def exhausted(self, tokens: int) -> str | None:
        # Names the first breached budget so the caller learns why the board stopped early.
        if self.max_tokens is not None and tokens >= self.max_tokens:
            return "max-tokens"
        if self.max_cost_usd is not None and self.cost_of(tokens) >= self.max_cost_usd:
            return "max-cost"
        return None


@dataclass(frozen=True, slots=True)
class TaskBoardPrefix:
    """Where a resumed board starts in execution order and what its stored steps achieved."""

    start_index: int
    completed: int
    failed: int
    total_tokens: int
    replay_indices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskBoardTurn:
    """One finished agent turn: the prompt it read, what it produced, what it cost."""

    prompt: str
    summary: str
    result_text: str
    thread_id: str
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class TaskBoardTaskOutcome:
    """One task attempt result plus subtasks accepted by its native tool, if any."""

    turn: TaskBoardTurn | None
    note: str
    subtasks: tuple[str, ...] = ()


class TaskBoardExecutionType(StrEnum):
    """Which loop structure a board run follows."""

    LINEAR = "linear"
    DAG = "dag"


class TaskBoardSettings(BaseModel):
    """Bounded, frozen task-board settings for one admitted local invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tasks: tuple[str, ...] = Field(
        min_length=1,
        max_length=500,
        description=(
            "The ordered board of work, where every entry is one complete task statement that "
            "one Codex agent has to finish on its own. Position is meaningful: task N runs only "
            "after tasks 0 through N-1 have been attempted, and its agent can be given the "
            "results of the tasks immediately before it. Entries arrive either as literal task "
            "strings or as the whole text of one Markdown task file each, and the board never "
            "reorders, merges, or splits what it was given. A board holds between 1 and 500 "
            "tasks, and no single task may exceed 20,000 characters."
        ),
    )
    window: int = Field(
        ge=0,
        le=25,
        default=10,
        description=(
            "How many immediately preceding task results the next agent is allowed to read, "
            "counted backwards from the task about to run. With a window of 10, the agent for "
            "task 90 receives summaries of tasks 80 through 89 and nothing earlier, which is "
            "what keeps prompt size flat as the board grows. A window of 0 gives an agent only "
            "its own task while still telling it that earlier tasks ran, and a window larger "
            "than the number of finished tasks simply clamps to what exists. This setting is "
            "ignored entirely when the context mode is isolated."
        ),
    )
    context_mode: TaskBoardContextMode = Field(
        default=TaskBoardContextMode.WINDOWED_SUMMARIES,
        description=(
            "Whether an agent is told anything about the tasks that ran before it. In "
            "windowed-summaries mode each agent reads bounded summaries of the previous window "
            "results, which suits a board whose tasks build on one another. In isolated mode no "
            "prior result reaches any agent and the prompt carries no prior-results section at "
            "all, which is the correct choice for a board of independently decomposed tasks "
            "that must not inherit each other's assumptions. Isolated mode overrides the window "
            "and summary settings rather than combining with them."
        ),
    )
    summary_mode: TaskBoardSummaryMode = Field(
        default=TaskBoardSummaryMode.TRUNCATE_TAIL,
        description=(
            "The shape of each prior-result summary once that result is longer than the "
            "character budget. In truncate-tail mode the summary keeps the opening of the "
            "result and names how many characters were dropped, which favors setup and "
            "reasoning. In head-tail mode the budget is split evenly between the opening and "
            "the closing of the result, which is what preserves a concluding answer or a final "
            "file listing. Neither mode calls a model, so summarization stays deterministic "
            "and free, and this setting does nothing in isolated context mode."
        ),
    )
    summary_max_chars: int = Field(
        ge=100,
        le=8000,
        default=1200,
        description=(
            "The character budget for one prior-result summary before the summary mode starts "
            "dropping content. A result at or under this length is passed through untouched, "
            "and anything longer is shortened and marked with the number of characters removed. "
            "Multiply this budget by the window to predict the worst-case size of the "
            "prior-results block a single agent will read. Accepted values run from 100 to "
            "8000 characters, and this setting does nothing in isolated context mode."
        ),
    )
    stop_on_error: bool = Field(
        default=True,
        description=(
            "What the board does the first time a task exhausts its retries. When enabled the "
            "board halts immediately, keeps every result completed before the failure, and "
            "returns that prefix rather than running work that depends on a task that never "
            "finished. When disabled the failed task is recorded with a failed status, a short "
            "placeholder stands in for its summary so board indices stay aligned, and the next "
            "task starts anyway. Leave it enabled for a dependent board and disable it for a "
            "board of independent tasks where one failure should not cancel the rest."
        ),
    )
    max_retries_per_task: int = Field(
        ge=0,
        le=3,
        default=1,
        description=(
            "How many extra attempts one task receives after its first attempt fails, before "
            "the board treats that task as failed. Every retry re-sends the identical prompt "
            "to a brand-new agent, so a retry recovers from a crashed or timed-out host rather "
            "than from a task the agent understood but could not do. Each attempt is charged "
            "against the caller's own model account, so a high retry count on a large board "
            "multiplies model cost. Accepted values run from 0 to 3, and a completed retry "
            "produces exactly one result entry, never a duplicate."
        ),
    )
    handoff_mode: TaskBoardHandoffMode = Field(
        default=TaskBoardHandoffMode.SUMMARY,
        description=(
            "What a finished task actually hands to the later tasks allowed to read it. In "
            "summary mode, the default, a reader sees only the bounded summary of each prior "
            "result, which is what keeps prompts flat on a long board. In task-and-summary mode "
            "each entry is prefixed with the prior task's own statement, so a reader learns "
            "what was asked as well as what came back. In full-result mode the untruncated "
            "result text is forwarded instead, which is accurate but grows prompts without "
            "bound and suits only short boards. This setting does nothing in isolated mode."
        ),
    )
    agent: TaskBoardAgentSettings = Field(
        default_factory=TaskBoardAgentSettings,
        description=(
            "The Codex agent configuration each iteration of the board is constructed with, "
            "covering model, sandbox authority, reasoning effort, and per-attempt timeout. One "
            "configuration applies to every task, because a board whose agents differ task by "
            "task would make its results incomparable and its cost unpredictable. The defaults "
            "reproduce the behavior a board had before these controls existed. Every field here "
            "affects the caller's own provider bill rather than the flat Vidbyte admission."
        ),
    )
    execution_type: TaskBoardExecutionType = Field(
        default=TaskBoardExecutionType.LINEAR,
        description=(
            "Which loop structure the board run follows. In linear mode tasks run in board "
            "order 0 through N-1 and each agent reads bounded summaries of the immediately "
            "preceding window tasks, which preserves the original board behavior exactly. In "
            "dag mode tasks run once each in deterministic topological order and each agent "
            "reads only its direct dependencies' summaries, so an independent task never pays "
            "for unrelated context. Execution stays sequential in both modes with one fresh "
            "agent per task; dag mode ignores the window for context selection."
        ),
    )
    dependencies: tuple[tuple[int, int], ...] = Field(
        default=(),
        description=(
            "The directed dependency links as sorted unique child-parent index pairs, where "
            "each pair means the child task reads the parent task's summary and runs only "
            "after it. Indices are 0-based board positions, so 8:2 means task 8 depends on "
            "task 2. Links are accepted only in dag mode and must form an acyclic graph with "
            "no self-links or duplicates; an empty set means every task is independent and "
            "runs in board order with empty dependency context."
        ),
    )
    allow_decompose: bool = Field(
        default=False,
        description=(
            "Whether a task's agent may call the native decompose_tool to replace its current "
            "task with an ordered list of self-contained subtasks that run in its place. The "
            "default is off and preserves the normal linear, DAG, windowed-context, and "
            "checkpoint behavior exactly. When enabled, the board runs as a mutable linear "
            "list: an accepted split is spliced in at the parent's position, every later task "
            "shifts right, and the children run one at a time before anything after them. "
            "Every parent and child runs isolated, so no agent reads prior summaries, and each "
            "child sees only its own subtask string. Children are never offered the tool, "
            "which keeps decomposition to exactly one level. Because a splice moves board "
            "indices while the run is in progress, the command rejects this setting together "
            "with checkpointing or DAG execution before any credential, payment, or agent."
        ),
    )
    max_subtasks: int = Field(
        ge=2,
        le=10,
        default=5,
        description=(
            "The maximum number of child tasks one parent may create in a single "
            "decompose_tool call, between 2 and 10, and it has no effect unless "
            "allow_decompose is true. The default of 5 separates the distinct pieces of a "
            "broad task without letting one parent fan out into many small billed turns. "
            "Candidates are stripped, entries that are blank or longer than the board's "
            "20,000-character task limit are dropped, and case-insensitive duplicates keep "
            "only their first occurrence before this cap truncates the remainder. A call left "
            "with fewer than two valid children is rejected, so the parent's task stays whole "
            "and its own final text becomes the result. The board-wide ceiling of 500 live "
            "tasks still applies, so a parent near that ceiling receives a smaller effective "
            "cap, and one with room for fewer than two children is not offered the tool."
        ),
    )

    @model_validator(mode="after")
    def validate_dependencies(self) -> TaskBoardSettings:
        # Rejects dangling, reflexive, repeated, or cyclic links before paid admission.
        count = len(self.tasks)
        seen: set[tuple[int, int]] = set()
        for child, parent in self.dependencies:
            if child < 0 or parent < 0 or child >= count or parent >= count:
                raise ValueError("dependency indices must reference board positions")
            if child == parent:
                raise ValueError("a task cannot depend on itself")
            if (child, parent) in seen:
                raise ValueError("duplicate dependency link")
            seen.add((child, parent))
        if seen and self.topological_order(count, self.dependencies) is None:
            raise ValueError("dependency links must form an acyclic graph")
        return self

    def execution_order(self) -> tuple[int, ...]:
        # The one order a board runs, resumes, replays, and forks in. A linear board runs in
        # board order; a DAG board runs parents first. `--from N` and `fork --at N` count
        # positions in this order, so they mean the same thing for both execution types.
        if self.execution_type is TaskBoardExecutionType.LINEAR:
            return tuple(range(len(self.tasks)))
        return self.topological_order(len(self.tasks), self.dependencies) or ()

    @staticmethod
    def topological_order(count: int, edges: tuple[tuple[int, int], ...]) -> tuple[int, ...] | None:
        # Kahn's algorithm with ties broken by the smallest index, so one board always yields
        # one order. None means a cycle kept some task from ever becoming ready.
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
        return tuple(order) if len(order) == count else None


class TaskBoardStepResult(BaseModel):
    """One task outcome with its bounded summary for downstream agents."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int = Field(ge=0)
    task: str = Field(min_length=1, max_length=20_000)
    summary: str = Field(min_length=1, max_length=8000)
    status: Literal["completed", "failed"]
    thread_id: str = Field(min_length=1, max_length=128)


class TaskBoardCheckpoint(BaseModel):
    """One durably stored step: prompt, outcome, usage, and its link to the step before."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    index: int = Field(ge=0)
    # The link that makes stored steps a list rather than a bag: it names the step this one
    # actually read, which after a fork is a step that lives in the parent board's directory.
    parent_index: int | None = Field(default=None, ge=0)
    task: str = Field(min_length=1, max_length=20_000)
    prompt: str = Field(min_length=1, max_length=220_000)
    summary: str = Field(min_length=1, max_length=8000)
    result_text: str = Field(default="", max_length=220_000)
    status: Literal["completed", "failed"]
    thread_id: str = Field(min_length=1, max_length=128)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    admission_id: str = Field(min_length=1, max_length=128)
    created_at: datetime


class TaskBoardCheckpointChain(BaseModel):
    """One board's stored steps as a linked list, plus the fork edge to its parent board."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    parent_board_id: str | None = Field(default=None, min_length=1, max_length=64)
    forked_at_index: int | None = Field(default=None, ge=0)
    task_count: int = Field(ge=0)
    nodes: tuple[TaskBoardCheckpoint, ...] = ()

    def head(self) -> TaskBoardCheckpoint | None:
        # The furthest step reached, which is where a resume continues from.
        return max(self.nodes, key=lambda node: node.index, default=None)

    def node_at(self, index: int) -> TaskBoardCheckpoint | None:
        # Direct addressing, because stored indices can be sparse after a replay or repair.
        return next((node for node in self.nodes if node.index == index), None)

    def ancestors_of(self, index: int) -> tuple[TaskBoardCheckpoint, ...]:
        # Walks parent_index backwards, so a caller sees the exact chain a step was built on
        # rather than every lower index that happens to sit in the same directory.
        walked: list[TaskBoardCheckpoint] = []
        seen: set[int] = set()
        cursor = self.node_at(index)
        while cursor is not None and cursor.parent_index is not None:
            if cursor.parent_index in seen:
                break
            seen.add(cursor.parent_index)
            cursor = self.node_at(cursor.parent_index)
            if cursor is not None:
                walked.append(cursor)
        return tuple(reversed(walked))

    @property
    def completed_indices(self) -> tuple[int, ...]:
        return tuple(sorted(node.index for node in self.nodes if node.status == "completed"))

    @property
    def failed_indices(self) -> tuple[int, ...]:
        return tuple(sorted(node.index for node in self.nodes if node.status == "failed"))

    @property
    def pending_indices(self) -> tuple[int, ...]:
        stored = {node.index for node in self.nodes}
        return tuple(index for index in range(self.task_count) if index not in stored)

    @property
    def total_tokens(self) -> int:
        return sum(node.total_tokens or 0 for node in self.nodes)


class TaskBoardResult(BaseModel):
    """Final local output: per-task summaries plus where the board lives and how to continue."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    admission_id: str = Field(min_length=1, max_length=128)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    steps: tuple[TaskBoardStepResult, ...]
    board_id: str | None = Field(default=None, min_length=1, max_length=64)
    board_dir: str | None = Field(default=None, min_length=1, max_length=4096)
    export_file: str | None = Field(default=None, min_length=1, max_length=4096)
    report_file: str | None = Field(default=None, min_length=1, max_length=4096)
    resume_command: str | None = Field(default=None, min_length=1, max_length=4096)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    stopped_reason: str | None = Field(default=None, min_length=1, max_length=64)
    text: str


class TaskBoardBoardSummary(BaseModel):
    """One row of the board index: identity, progress, and where the board lives."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    task_count: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    pending: int = Field(ge=0)
    parent_board_id: str | None = Field(default=None, min_length=1, max_length=64)


class TaskBoardUnreadableBoard(BaseModel):
    """One board the index found but could not load, with the failure's own repair advice."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    problem: str = Field(min_length=1, max_length=1000)
    hint: str = Field(default="", max_length=1000)


@dataclass(frozen=True, slots=True)
class TaskBoardIndex:
    """Every board under one checkpoint root, split into loadable and unreadable."""

    boards: tuple[TaskBoardBoardSummary, ...]
    unreadable: tuple[TaskBoardUnreadableBoard, ...]


class TaskBoardListing(BaseModel):
    """Every board stored under one checkpoint root, newest progress first."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    checkpoint_root: str = Field(min_length=1, max_length=4096)
    boards: tuple[TaskBoardBoardSummary, ...] = ()
    unreadable: tuple[TaskBoardUnreadableBoard, ...] = ()
    text: str


class TaskBoardStatusReport(BaseModel):
    """One board's offline progress, spend, and the command that continues it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    task_count: int = Field(ge=0)
    completed_indices: tuple[int, ...] = ()
    failed_indices: tuple[int, ...] = ()
    pending_indices: tuple[int, ...] = ()
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    parent_board_id: str | None = Field(default=None, min_length=1, max_length=64)
    report_file: str | None = Field(default=None, min_length=1, max_length=4096)
    resume_command: str = Field(min_length=1, max_length=4096)
    text: str


class TaskBoardStepDetail(BaseModel):
    """Everything stored for one step, so inspecting it costs one call and no file reads."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    step_file: str = Field(min_length=1, max_length=4096)
    step: TaskBoardCheckpoint
    ancestors: tuple[int, ...] = ()
    text: str


class TaskBoardForkResult(BaseModel):
    """A new board carrying a copy of another board's prefix, and how to continue it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    parent_board_id: str = Field(min_length=1, max_length=64)
    forked_at_index: int = Field(ge=0)
    copied_steps: int = Field(ge=0)
    resume_command: str = Field(min_length=1, max_length=4096)
    text: str


class TaskBoardPromptPreview(BaseModel):
    """The exact prompt one step would receive, rebuilt without starting any agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    board_dir: str = Field(min_length=1, max_length=4096)
    index: int = Field(ge=0)
    prompt: str = Field(min_length=1, max_length=220_000)
    text: str


class TaskBoardTaskExport(BaseModel):
    """A board's task list written back out as a reviewable file."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    board_id: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=4096)
    task_count: int = Field(ge=1)
    text: str


class PersistenceStrength(IntEnum):
    """The six caller-facing persistence tiers, from lightest to most insistent."""

    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4
    TIER_5 = 5
    TIER_6 = 6


_PERSISTENCE_REPEAT_COUNTS: Mapping[PersistenceStrength, int] = {
    PersistenceStrength.TIER_1: 6,
    PersistenceStrength.TIER_2: 8,
    PersistenceStrength.TIER_3: 20,
    PersistenceStrength.TIER_4: 40,
    PersistenceStrength.TIER_5: 70,
    PersistenceStrength.TIER_6: 100,
}


class PersistenceSettings(BaseModel):
    """Bounded, frozen persistence-primitive settings for a future executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    strength: PersistenceStrength

    @property
    def repeat_count(self) -> int:
        # Resolves the caller-facing tier to its fixed continuation-turn count.
        return _PERSISTENCE_REPEAT_COUNTS[self.strength]


@dataclass(frozen=True, slots=True)
class RuntimeAdmissionCheck:
    """One deterministic check with a typed reason instead of string/None sentinels."""

    reason: AdmissionReason

    @property
    def passed(self) -> bool:
        return self.reason is AdmissionReason.PASSED


class RuntimeAdmissionVerdict(BaseModel):
    """Deterministic gate result that the executor requires before spawning."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    admitted: bool
    admission_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=160)
    reason: str | None = None


class RuntimeGrantVerificationRequest(BaseModel):
    """Proof sent only to the authenticated backend, never to a model."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    grant_token: str = Field(min_length=10, max_length=8192)
    idempotency_key_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PersistenceResult(BaseModel):
    """Final local output with deterministic completed-turn accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    session_id: str
    continuation_turns: int
    text: str


class StageSandbox(StrEnum):
    """Filesystem and network reach one stage's agent runs under."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


class StageEffort(StrEnum):
    """How much reasoning one stage's agent spends before it answers."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class StageSummary(StrEnum):
    """How much of its reasoning one stage's agent reports back."""

    NONE = "none"
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"


class StageApproval(StrEnum):
    """What one stage's agent does when an action needs approval."""

    AUTO_REVIEW = "auto_review"
    DENY_ALL = "deny_all"


class StagePersonality(StrEnum):
    """Response personality one stage's agent writes in."""

    NONE = "none"
    FRIENDLY = "friendly"
    PRAGMATIC = "pragmatic"


class StageSpec(BaseModel):
    """One caller-defined stage mapping to exactly one fresh Codex agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "A short label for this stage, used as the agent's name and in progress output. It "
            "identifies the stage in results and in any failure, so make it say what the stage "
            "does rather than where it sits in the order. Names are not required to be unique "
            "and are never sent to the backend with the admission request. Position in the "
            "stage list, not this name, is what decides when a stage runs."
        ),
    )
    prompt: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "The turn prompt this stage's agent is given, and the only instruction it receives "
            "for the work itself. The token {{previous}} is replaced before the turn starts: in "
            "sequential mode it becomes the previous stage's full output, and for the first "
            "stage, or for every stage in parallel mode, it becomes the top-level task. Write "
            "it as a complete instruction, because the agent has no thread history to fall back "
            "on. A prompt that is empty or only whitespace is rejected before admission."
        ),
    )
    system_prompt: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "The system prompt that shapes this stage's agent for its single turn. Each stage "
            "gets its own, which is the whole point of staging: an auditing stage and an "
            "implementing stage need different standing instructions, and one shared prompt "
            "serves neither well. It is applied when the agent is built, before the turn runs, "
            "and never carries over to another stage. Like the turn prompt, it may not be empty "
            "or whitespace only."
        ),
    )
    model: str = Field(
        default="",
        max_length=128,
        description=(
            "The model id this stage's agent runs on, such as gpt-5.1-codex. Leave it empty to "
            "accept whatever model the installed Codex is configured to use, which is the right "
            "choice unless a stage genuinely needs a different one. This is the one stage "
            "setting with an open value set, so an unrecognized id is not caught locally and "
            "fails inside Codex after admission has already been charged. Set it per stage when "
            "a cheap model can do the early stages and only the last stage needs a strong one."
        ),
    )
    effort: StageEffort = Field(
        default=StageEffort.MEDIUM,
        description=(
            "How much reasoning this stage's agent spends before it answers, from none through "
            "xhigh. Higher effort costs more tokens on your own OpenAI account and takes longer, "
            "and it is the setting that most changes what a stage is capable of. Analysis and "
            "planning stages usually justify high; mechanical stages rarely do. The value is one "
            "of the closed set the CLI accepts, so a misspelling fails at parse time rather than "
            "silently falling back to a default."
        ),
    )
    summary: StageSummary = Field(
        default=StageSummary.AUTO,
        description=(
            "How much of its own reasoning this stage's agent reports alongside its answer. auto "
            "lets Codex decide, none suppresses the summary entirely, and concise and detailed "
            "ask for progressively more. This affects what you read, not what the agent does, so "
            "it changes neither the result nor the price of the run. Choose detailed when the "
            "point of a stage is to show its reasoning to a later stage. The value is drawn from "
            "a closed set the CLI validates before anything is charged."
        ),
    )
    sandbox: StageSandbox = Field(
        default=StageSandbox.WORKSPACE_WRITE,
        description=(
            "How far this stage's agent may reach into the filesystem: read-only, "
            "workspace-write, or full-access. Sandboxing is enforced by Codex itself rather than "
            "by this CLI, so it is a real boundary and not a hint. Give read-only to stages that "
            "only inspect or plan, and keep workspace-write for the stages that actually change "
            "files. full-access exists for the rare stage that must reach outside the working "
            "directory, and it is never the right default for an unattended run."
        ),
    )
    approval: StageApproval = Field(
        default=StageApproval.AUTO_REVIEW,
        description=(
            "What this stage's agent does when an action needs approval and no person is there "
            "to give it. auto_review lets Codex review and proceed on its own, which is what "
            "keeps an unattended staged run moving. deny_all refuses every such action instead, "
            "which is the safe choice for a stage that should only ever read. Because a staged "
            "run is not interactive, neither value ever prompts you. Both are validated against "
            "a closed set before the wallet is touched."
        ),
    )
    personality: StagePersonality = Field(
        default=StagePersonality.NONE,
        description=(
            "The response personality this stage's agent writes in: none, friendly, or "
            "pragmatic. It changes tone and framing only, never capability, tool use, or "
            "sandboxing. It is worth setting when a stage's output is read by a person and worth "
            "leaving at none when the output is consumed by the next stage. Like the other "
            "closed-set settings, an unrecognized value is rejected at parse time. Each stage "
            "carries its own, so stages need not agree."
        ),
    )
    additional_context: str = Field(
        default="",
        max_length=20_000,
        description=(
            "Extra turn-scoped context handed to this stage's agent alongside its prompt, for "
            "material that is reference rather than instruction. It is applied to this stage "
            "only and never reaches another stage, so shared context has to be repeated on each "
            "stage that needs it. Leave it empty when the prompt already says everything. It "
            "counts against the same token budget the prompt does, billed to your own OpenAI "
            "account."
        ),
    )
    image: str = Field(
        default="",
        max_length=4096,
        description=(
            "One image input handed to this stage's agent alongside its text prompt, either as "
            "an https:// URL or a data: URL, or as a local image file path. A value starting "
            "with https://, http://, or data: is sent as a remote image URL, and anything else "
            "is sent as a local image path, which is the correct choice for a screenshot the "
            "stage must review. Leave it empty when the stage needs no image, which is the "
            "common case. A value that is only whitespace is rejected before admission."
        ),
    )
    skill: str = Field(
        default="",
        max_length=2048,
        description=(
            "One native Codex skill handed to this stage's agent, written as NAME=PATH where "
            "NAME is the skill name and PATH is the skill directory the agent should load. "
            "The separator is the first equals sign, so PATH itself may contain further equals "
            "signs. Leave it empty when the stage needs no skill. A value without the separator, "
            "or with a blank name or path, is rejected before admission."
        ),
    )
    mention: str = Field(
        default="",
        max_length=2048,
        description=(
            "One named resource mention handed to this stage's agent, written as NAME=PATH "
            "where NAME is the resource name and PATH is the resource path the agent should "
            "read. The separator is the first equals sign, so PATH itself may contain further "
            "equals signs. Leave it empty when the stage needs no mention. A value without the "
            "separator, or with a blank name or path, is rejected before admission."
        ),
    )
    output_schema: str = Field(
        default="",
        max_length=20_000,
        description=(
            "A JSON object schema string forcing this stage's agent to answer in a fixed shape, "
            "so the next stage can check the handoff mechanically instead of re-reading prose. "
            'For example a review stage can be forced to return {"files": [...], "summary": '
            '"..."}. The value must parse as a JSON object when given, and an empty value '
            "means the stage answers in free prose. A value that is not a JSON object is "
            "rejected before admission."
        ),
    )

    @field_validator("name", "prompt", "system_prompt")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        # Whitespace-only stage text would burn a paid turn on nothing.
        if not value.strip():
            raise ValueError("must contain non-whitespace characters")
        return value

    @field_validator("image")
    @classmethod
    def _reject_blank_image(cls, value: str) -> str:
        # An explicit blank image would send an empty input item to the SDK.
        if value != "" and not value.strip():
            raise ValueError("must contain non-whitespace characters")
        return value

    @field_validator("skill", "mention")
    @classmethod
    def _reject_malformed_reference(cls, value: str) -> str:
        # NAME=PATH is the only shape the adapter can split without guessing.
        if value == "":
            return value
        name, separator, path = value.partition("=")
        if not separator or not name.strip() or not path.strip():
            raise ValueError("must be NAME=PATH with non-blank parts")
        return value

    @field_validator("output_schema")
    @classmethod
    def _reject_malformed_schema(cls, value: str) -> str:
        # The adapter passes the parsed object to the SDK, so only an object parses.
        if value == "":
            return value
        try:
            parsed: object = json.loads(value)
        except ValueError as error:
            raise ValueError("must parse as a JSON object") from error
        if not isinstance(parsed, dict):
            raise ValueError("must parse as a JSON object")
        return value


class StagesSettings(BaseModel):
    """Bounded, frozen stages-primitive settings for the stages executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    stages: tuple[StageSpec, ...] = Field(
        min_length=1,
        max_length=StagesLimit.MAX_STAGES,
        description=(
            "The ordered stages of this run, where entry i is the complete configuration for "
            "the agent that runs stage i. Every stage gets a brand-new agent that is discarded "
            "when its turn ends, so no thread state, no tool state, and no history ever crosses "
            "a stage boundary. Order is meaningful in sequential mode and ignored in parallel "
            "mode. A run holds between 1 and 25 stages, and the one-cent admission covers all "
            "of them however many there are."
        ),
    )
    parallel: bool = Field(
        default=False,
        description=(
            "Whether the stages run all at once instead of one after another. Sequential, the "
            "default, awaits each stage before starting the next and substitutes the finished "
            "output into the next stage's {{previous}} token, which is what lets stages build "
            "on each other. Parallel starts every stage together with asyncio.gather and gives "
            "each one the top-level task as {{previous}}, so stages must not depend on each "
            "other's results. Parallel finishes sooner but runs every stage's model calls "
            "concurrently against your own OpenAI account."
        ),
    )
    stop_on_error: bool = Field(
        default=True,
        description=(
            "What the run does the first time a stage exhausts its retries. When enabled the "
            "run halts immediately, keeps every result completed before the failure, and "
            "returns that prefix rather than running work that depends on a stage that never "
            "finished. When disabled the failed stage is recorded with a failed status, a short "
            "placeholder stands in for its text so stage indices stay aligned, and the next "
            "stage starts anyway. Leave it enabled for a dependent run and disable it for "
            "independent stages where one failure should not cancel the rest."
        ),
    )
    max_retries_per_stage: int = Field(
        ge=0,
        le=3,
        default=1,
        description=(
            "How many extra attempts one stage receives after its first attempt fails, before "
            "the run treats that stage as failed. Every retry re-sends the identical prompt "
            "to a brand-new agent, so a retry recovers from a crashed or timed-out host rather "
            "than from a stage the agent understood but could not do. Each attempt is charged "
            "against the caller's own model account, so a high retry count on a long run "
            "multiplies model cost. Accepted values run from 0 to 3, and a completed retry "
            "produces exactly one result entry, never a duplicate."
        ),
    )


class StageStepResult(BaseModel):
    """One stage outcome with its identity and attempt accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=64)
    status: Literal["completed", "failed"]
    thread_id: str = Field(min_length=1, max_length=128)
    attempts: int = Field(ge=1)
    duration_ms: int = Field(ge=0)


class StagesResult(BaseModel):
    """Ordered per-stage outputs with per-stage accounting for partial runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    admission_id: str = Field(min_length=1, max_length=128)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    steps: tuple[StageStepResult, ...]
    stage_texts: tuple[str, ...]
    text: str
