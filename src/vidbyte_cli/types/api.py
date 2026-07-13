"""Response envelope and resource models mirroring the Vidbyte backend public API DTOs.

Keep field names in sync with backend/lib/dtos/harness.py once those routes ship. These
are the pydantic "dataclasses" every command and harness passes around; the CLI never
hand-builds raw dicts for a request or parses a raw dict from a response.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

RunStatus = Literal["queued", "running", "completed", "failed"]


class ApiError(BaseModel):
    # Structured backend error; mapped to a CliError before it ever reaches the user.
    code: str
    title: str
    detail: str


class ApiPagination(BaseModel):
    limit: int
    page: int
    total: int | None = None


class ApiEnvelope(BaseModel, Generic[T]):
    # Standard response wrapper the ApiClient unwraps so callers see only `data`.
    success: bool
    message: str | None = None
    data: T | None = None
    error: ApiError | None = None
    pagination: ApiPagination | None = None


class HarnessRepoRef(BaseModel):
    # Identifies exactly which code a run executes against.
    url: str
    sha: str
    branch: str | None = None


class HarnessRunCreateRequest(BaseModel):
    # A run is an invocation of a specific harness *command* with typed params, not just a
    # free-text task (resolves the types/api.ts:30 review comment). Every dynamically built
    # harness command collapses to this one envelope, so the CLI needs no per-harness request
    # code. `args` are positional inputs; `options` are flags; both validate against the
    # harness manifest before submission.
    harness: str
    command: str
    args: dict[str, object] = Field(default_factory=dict)
    options: dict[str, object] = Field(default_factory=dict)
    repo: HarnessRepoRef


class HarnessRunEvent(BaseModel):
    type: Literal["status", "log", "error"]
    message: str
    created_at: str


class HarnessRunResult(BaseModel):
    branch: str | None = None
    pr_url: str | None = None
    summary: str | None = None


class HarnessRun(BaseModel):
    run_id: str
    harness: str
    command: str
    status: RunStatus
    args: dict[str, object] = Field(default_factory=dict)
    options: dict[str, object] = Field(default_factory=dict)
    repo: HarnessRepoRef
    events: list[HarnessRunEvent] = Field(default_factory=list)
    result: HarnessRunResult | None = None
    created_at: str
    updated_at: str


class HarnessSummary(BaseModel):
    # One entry in the available-harness catalog (distinct from a run).
    name: str
    description: str
    version: str


class WhoAmI(BaseModel):
    user_id: str
    email: str | None = None
