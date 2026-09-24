"""Wire and local contracts for the rules agent.

The wire models mirror the hosted `runtime.rules@1` batch route. Requests forbid extra fields
so a typo fails before a paid call; responses ignore unknown fields so a backend addition never
breaks an installed CLI. The local models describe one durable scan on disk: its frozen scope and
limits, the prompt IDs in each batch, and each finished batch's result. No model here stores
prompt text on disk; only batch requests carry it, and only in memory.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ..lib.constants.rules import RulesBackendLimit

RULES_SCHEMA_VERSION = 1


class RulesHost(StrEnum):
    """Coding-agent hosts whose saved transcripts the rules agent can read."""

    CLAUDE = "claude"
    CODEX = "codex"
    GROK = "grok"
    OPENCODE = "opencode"


class RuleScope(StrEnum):
    """How widely one written rule is meant to apply."""

    GLOBAL = "global"
    PROJECT = "project"
    HOST = "host"


class RulesScanStatus(StrEnum):
    """Where one stored scan stands."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"


class RulesStopReason(StrEnum):
    """Why a scan stopped before every batch completed."""

    SPEND_LIMIT = "spend_limit"
    TIME_LIMIT = "time_limit"
    CREDIT_EXHAUSTED = "credit_exhausted"
    BATCH_FAILED = "batch_failed"


class RulesPromptPayload(BaseModel):
    """One user-typed prompt as the batch route accepts it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    prompt_id: str
    host: RulesHost
    session_id: str
    text: str = Field(min_length=1, max_length=RulesBackendLimit.PROMPT_MAX_CHARS)
    project: str | None = None
    created_at: datetime | None = None


class RulesBatchRequest(BaseModel):
    """One paid batch request."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    scan_id: str
    batch_index: int = Field(ge=0)
    max_cost_cents: int = Field(ge=1, le=RulesBackendLimit.MAX_BATCH_COST_CENTS)
    prompts: list[RulesPromptPayload] = Field(
        min_length=1, max_length=RulesBackendLimit.BATCH_MAX_PROMPTS
    )


class Rule(BaseModel):
    """One standing rule the hosted writer produced, citing prompt IDs as evidence."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    title: str
    rule: str
    applies_when: str
    scope: RuleScope
    rationale: str
    evidence_prompt_ids: list[str] = Field(default_factory=list)


class RulesBatchResult(BaseModel):
    """What one batch classified, flagged, wrote, and charged."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    scan_id: str
    batch_index: int
    prompt_count: int
    classified_count: int
    unclassified_count: int
    flagged_prompt_ids: list[str] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    charged_cents: int = Field(ge=0)
    model: str | None = None


class RulesScanScope(BaseModel):
    """Which transcripts a scan reads; stored whole so resume needs no flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    hosts: list[RulesHost]
    since: datetime | None = None
    until: datetime | None = None
    project: str | None = None
    max_sessions: int | None = None
    max_prompts: int | None = None


class RulesScanLimits(BaseModel):
    """How much a scan may spend, how long it may run, and how it batches."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    max_spend_cents: int = Field(ge=1)
    max_batch_cost_cents: int = Field(ge=1, le=RulesBackendLimit.MAX_BATCH_COST_CENTS)
    batch_size: int = Field(ge=1, le=RulesBackendLimit.BATCH_MAX_PROMPTS)
    time_limit_seconds: int | None = Field(default=None, ge=1)


class RulesScanManifest(BaseModel):
    """One durable scan: frozen input, batch plan, and progress so far."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = RULES_SCHEMA_VERSION
    scan_id: str
    created_at: datetime
    updated_at: datetime
    scope: RulesScanScope
    limits: RulesScanLimits
    batches: list[list[str]]
    completed_batches: list[int] = Field(default_factory=list)
    spent_cents: int = Field(default=0, ge=0)
    rule_count: int = Field(default=0, ge=0)
    status: RulesScanStatus = RulesScanStatus.PLANNED
    stop_reason: RulesStopReason | None = None
    document_path: str | None = None

    @property
    def prompt_count(self) -> int:
        # Counts every planned prompt across all batches.
        return sum(len(batch) for batch in self.batches)

    @property
    def pending_batches(self) -> list[int]:
        # Returns batch indexes still to run, in plan order.
        done = set(self.completed_batches)
        return [index for index in range(len(self.batches)) if index not in done]


class RulesBatchRecord(BaseModel):
    """One finished batch as stored beside its scan manifest."""

    model_config = ConfigDict(extra="forbid")
    batch_index: int = Field(ge=0)
    completed_at: datetime
    result: RulesBatchResult
