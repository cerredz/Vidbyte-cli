"""Typed contracts for the same-host ensemble runtime primitive.

`EnsembleInputs` is the whole command surface as one validated value, so a bound holds
whether the value came from Click or from a programmatic caller. `GeneratedRole` and
`RoleProposal` are the two structured-output schemas the agents themselves fill in.

Nothing here crosses the API boundary: the backend sees only admission metadata.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EnsembleHost(StrEnum):
    """Native hosts the ensemble can actually run on today."""

    CODEX = "codex"


class EnsembleReasoningEffort(StrEnum):
    """Reasoning-effort values the Codex integration accepts."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class EnsembleConfidence(StrEnum):
    """How strongly a role stands behind the approach it proposed."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EnsembleInputs(BaseModel):
    """Every caller-settable ensemble option, validated once as a single value."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    task: str = Field(min_length=1, max_length=20_000)
    host: EnsembleHost = EnsembleHost.CODEX
    roles: int = Field(default=3, ge=2, le=8)
    model: str | None = Field(default=None, max_length=128)
    reasoning_effort: EnsembleReasoningEffort | None = None
    role_timeout_seconds: int = Field(default=300, ge=1, le=3600)


class GeneratedRole(BaseModel):
    """One role the planner invented, as the four sections its prompt is built from."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=64)
    identity: str = Field(min_length=1, max_length=4_000)
    personality: str = Field(min_length=1, max_length=4_000)
    knowledge: str = Field(min_length=1, max_length=8_000)
    goal: str = Field(min_length=1, max_length=4_000)


class RolePlan(BaseModel):
    """The planner turn's structured output: the ensemble's whole roster."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    roles: tuple[GeneratedRole, ...] = Field(min_length=1, max_length=8)


class RoleProposal(BaseModel):
    """One read-only role's structured recommendation, never an edit."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    role: str = Field(min_length=1, max_length=64)
    approach: str = Field(min_length=1, max_length=20_000)
    risks: tuple[str, ...] = Field(default=(), max_length=20)
    files: tuple[str, ...] = Field(default=(), max_length=50)
    confidence: EnsembleConfidence


class EnsembleRoleFailure(BaseModel):
    """Why one role produced no proposal, in a closed machine-branchable vocabulary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    role: str = Field(min_length=1, max_length=64)
    reason: Literal["timeout", "host_error", "invalid_output"]


class EnsembleResult(BaseModel):
    """The complete outcome of one ensemble run, including its partial failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    task: str
    host: EnsembleHost
    roles: tuple[GeneratedRole, ...]
    proposals: tuple[RoleProposal, ...]
    failures: tuple[EnsembleRoleFailure, ...]
    implementation: str
    root_thread_id: str
    implementer_thread_id: str
    charged_cents: int
