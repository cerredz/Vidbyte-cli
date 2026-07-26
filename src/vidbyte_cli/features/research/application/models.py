"""FILE: src/vidbyte_cli/features/research/application/models.py

PURPOSE: Defines command-neutral research use-case inputs and mutation results.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..domain import ResearchRun, ResearchRunAccepted, ResearchRunRequest


class ResearchMutationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request: ResearchRunRequest
    idempotency_key: str | None = None
    wait: bool = True
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=86_400.0)


class ResearchResumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str | None = None
    wait: bool = True
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=86_400.0)


class ResearchMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: ResearchRunAccepted
    idempotency_key: str
    run: ResearchRun | None = None
