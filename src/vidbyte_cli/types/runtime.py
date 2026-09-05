"""Wire and local planning contracts for Vidbyte runtime primitives.

The backend sees only admission metadata; task and machine context stay local. Frozen,
extra-forbid models make contract drift fail before a paid execution can begin.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class RuntimeHostStatus(BaseModel):
    """Non-secret PATH discovery result for one native coding-agent host."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    host: RuntimeHost
    available: bool
    executable: str | None = None


class RuntimeLaunchPlan(BaseModel):
    """Local-only handoff a future executor will turn into an agent topology."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)
    capability_id: Literal["runtime.review.adversarial-team@1", "runtime.persistence@1"]
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
    PersistenceStrength.TIER_1: 3,
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
