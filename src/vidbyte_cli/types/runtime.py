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

from pydantic import BaseModel, ConfigDict, Field

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
    ] = "runtime.review.adversarial-team@1"
    host: RuntimeHost
    executable: Path
    working_directory: Path
    task: str = Field(min_length=1, max_length=20_000)


class TaskBoardSummaryMode(StrEnum):
    """How one prior task result is shrunk before the next agent reads it."""

    TRUNCATE_TAIL = "truncate-tail"
    HEAD_TAIL = "head-tail"


class TaskBoardSettings(BaseModel):
    """Bounded, frozen task-board settings for one admitted local invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    tasks: tuple[str, ...] = Field(
        min_length=1,
        max_length=500,
        description=("Ordered board tasks; task N runs in its own agent after tasks 0..N-1."),
    )
    window: int = Field(
        ge=0,
        le=25,
        default=10,
        description=("How many prior summaries the next agent sees; 0 means only its task."),
    )
    summary_mode: TaskBoardSummaryMode = Field(
        default=TaskBoardSummaryMode.TRUNCATE_TAIL,
        description=("Summary shape per prior result: truncate-tail prefix or head-tail."),
    )
    summary_max_chars: int = Field(
        ge=100,
        le=8000,
        default=1200,
        description=("Max characters kept per prior summary before markers are added."),
    )
    stop_on_error: bool = Field(
        default=True,
        description=("Stop at the first failed task instead of marking failed and continuing."),
    )
    max_retries_per_task: int = Field(
        ge=0,
        le=3,
        default=1,
        description=("Retries per task before failure; retries reuse the windowed prompt."),
    )


class TaskBoardStepResult(BaseModel):
    """One task outcome with its bounded summary for downstream agents."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int = Field(ge=0)
    task: str = Field(min_length=1, max_length=4000)
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
