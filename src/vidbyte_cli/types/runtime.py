"""Wire and local planning contracts for Vidbyte runtime primitives.

The backend sees only admission metadata; task and machine context stay local. Frozen,
extra-forbid models make contract drift fail before a paid execution can begin.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..lib.constants.runtime import AdmissionReason


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


class TaskBoardStepResult(BaseModel):
    """One task outcome with its bounded summary for downstream agents."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int = Field(ge=0)
    task: str = Field(min_length=1, max_length=20_000)
    summary: str = Field(min_length=1, max_length=8000)
    status: Literal["completed", "failed"]
    thread_id: str = Field(min_length=1, max_length=128)


class TaskBoardResult(BaseModel):
    """Final local output with per-task summaries in board order."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    admission_id: str = Field(min_length=1, max_length=128)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    steps: tuple[TaskBoardStepResult, ...]
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


class StageSpec(BaseModel):
    """One caller-defined stage mapping to exactly one fresh Codex agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=20_000)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    model: str = Field(default="", max_length=128)
    effort: str = Field(default="medium", max_length=32)
    summary: str = Field(default="auto", max_length=32)
    sandbox: str = Field(default="workspace-write", max_length=32)
    approval: str = Field(default="auto_review", max_length=32)
    personality: str = Field(default="none", max_length=32)
    additional_context: str = Field(default="", max_length=20_000)

    @field_validator("name", "prompt", "system_prompt")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        # Whitespace-only stage text would burn a paid turn on nothing.
        if not value.strip():
            raise ValueError("must contain non-whitespace characters")
        return value


class StagesSettings(BaseModel):
    """Bounded, frozen stages-primitive settings for the stages executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    stages: tuple[StageSpec, ...] = Field(min_length=1, max_length=10)
    parallel: bool = False


class StagesResult(BaseModel):
    """Ordered per-stage outputs with the final text last."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    stage_texts: tuple[str, ...]
    text: str
