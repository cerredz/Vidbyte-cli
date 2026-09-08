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
        "runtime.stages@1",
    ] = "runtime.review.adversarial-team@1"
    host: RuntimeHost
    executable: Path
    working_directory: Path
    task: str = Field(min_length=1, max_length=20_000)


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
