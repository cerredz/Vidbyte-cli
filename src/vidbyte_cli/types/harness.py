"""Harness resource models: runs, run inputs, and catalog entries.

Split out from types/api.py (which now holds only the transport envelope) so the two
concerns stay separate: `types/api.py` is *how* the CLI talks to the backend, this is
*what* a harness run is. Keep field names in sync with backend/lib/dtos/harness.py once
those routes ship. These are the pydantic "dataclasses" every command and harness passes
around; the CLI never hand-builds raw dicts for a request or parses one from a response.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal["queued", "running", "completed", "failed"]


class HarnessRepoRef(BaseModel):
    # Identifies exactly which code a run executes against. Only harnesses that operate on a
    # repo (e.g. software-engineering) attach one; see BaseHarness.requires_repo.
    url: str
    sha: str
    branch: str | None = None


class HarnessRunCreateRequest(BaseModel):
    # A run is an invocation of a specific harness *command* with typed params, not just a
    # free-text task (resolves the types/api.ts:30 review comment). Every dynamically built
    # harness command collapses to this one envelope, so the CLI needs no per-harness request
    # code. `args` are positional inputs; `options` are flags; both validate against the
    # harness manifest before submission. `repo` is optional: not every harness runs against
    # a git repository (resolves the base.py:47 review comment).
    harness: str
    command: str
    args: dict[str, object] = Field(default_factory=dict)
    options: dict[str, object] = Field(default_factory=dict)
    repo: HarnessRepoRef | None = None


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
    repo: HarnessRepoRef | None = None
    events: list[HarnessRunEvent] = Field(default_factory=list)
    result: HarnessRunResult | None = None
    created_at: str
    updated_at: str


class HarnessSummary(BaseModel):
    # One entry in the available-harness catalog (distinct from a run).
    name: str
    description: str
    version: str
