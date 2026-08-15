"""The research surface's wire shapes, its status vocabulary, and its two identifier guards.

A thread has two identifiers and the API publishes only one of them. `encrypted_id` is the
public share token every route accepts in a path; `thread_id` is internal and is rejected by
path validation before any lookup. So the models here bind the CLI's `thread_id` field to the
wire key `encrypted_id` by alias, deliberately leave `populate_by_name` off so the internal
key cannot populate it, and set `extra="ignore"` so it is discarded on arrival instead.

`ResearchRunStatus` declares no thread field at all, because the status route carries only
the internal identifier — a field the CLI must never print, since a user would paste it back.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from ..lib.errors.failures import ResearchIdempotencyKeyInvalid, ResearchThreadIdInvalid

# The backend pins a thread share token to a UUIDv4 and matches path segments against it in
# transport, so the same shape is checked locally before a request is ever spent.
_THREAD_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_MAX_PROMPT_CHARACTERS = 20_000


class ResearchStatus(StrEnum):
    """Every durable state a research run can report."""

    ADMITTING = "admitting"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CREDIT_EXHAUSTED = "credit_exhausted"

    def is_terminal(self) -> bool:
        # True once the backend will not move this run again without a continuation.
        return self in _TERMINAL_STATUSES

    def is_resumable(self) -> bool:
        # The three states the backend accepts a continuation from; anything else is a 409.
        return self in _RESUMABLE_STATUSES


_TERMINAL_STATUSES = frozenset(
    {
        ResearchStatus.COMPLETED,
        ResearchStatus.PARTIAL,
        ResearchStatus.FAILED,
        ResearchStatus.CANCELLED,
        ResearchStatus.CREDIT_EXHAUSTED,
    }
)
_RESUMABLE_STATUSES = frozenset(
    {ResearchStatus.PARTIAL, ResearchStatus.FAILED, ResearchStatus.CREDIT_EXHAUSTED}
)


class ResearchSize(StrEnum):
    """Preset breadth for a run, when the caller does not size it by hand."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ResearchKind(StrEnum):
    """The resource kinds discovery is allowed to return."""

    PAPER = "paper"
    WEB = "web"


class ThreadId:
    """One public research thread share token, validated on construction."""

    def __init__(self, value: str) -> None:
        self.value = value

    @classmethod
    def parse(cls, value: str) -> ThreadId:
        # Raises the usage failure locally rather than spending a request on a 422.
        candidate = value.strip()
        if not _THREAD_ID_PATTERN.fullmatch(candidate):
            raise ResearchThreadIdInvalid()
        return cls(candidate)

    @classmethod
    def normalize(cls, value: str) -> str:
        # The pydantic entry point: validating and canonicalizing are one operation.
        return str(cls.parse(value))

    def __str__(self) -> str:
        return self.value


class IdempotencyKey:
    """The key that lets one priced mutation be retried without being charged twice."""

    def __init__(self, value: str) -> None:
        self.value = value

    @classmethod
    def create(cls, explicit: str | None) -> IdempotencyKey:
        # A fresh key per invocation, unless the caller supplies one to replay a mutation.
        if explicit is None:
            return cls(str(uuid4()))
        candidate = explicit.strip()
        if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(candidate):
            raise ResearchIdempotencyKeyInvalid()
        return cls(candidate)

    def __str__(self) -> str:
        return self.value


NormalizedThreadId = Annotated[str, AfterValidator(ThreadId.normalize)]


class ResearchRunCreateRequest(BaseModel):
    """The body both `research start` and `research add` submit.

    Mirrors the backend request DTO field for field. Every optional field defaults to None so
    `exclude_none` drops it from the encoded body: the backend forbids unknown keys and
    requires a non-empty `resource_kinds` when the key is present, so an unset option has to
    be absent rather than null or empty.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=_MAX_PROMPT_CHARACTERS)
    # Version 2 is the backend default and the only version that carries reference artifacts.
    request_schema_version: Literal[2] = 2
    size: ResearchSize | None = None
    target_sources: int | None = Field(default=None, ge=1, le=1_000)
    search_calls: int | None = Field(default=None, ge=1, le=100)
    resource_kinds: list[ResearchKind] | None = Field(default=None, min_length=1, max_length=2)
    include_domains: list[str] | None = Field(default=None, max_length=50)
    exclude_domains: list[str] | None = Field(default=None, max_length=50)
    published_after: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    language: str | None = Field(default=None, min_length=2, max_length=12)
    max_run_cost_cents: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt cannot be blank")
        return normalized

    @field_validator("published_after")
    @classmethod
    def validate_published_after(cls, value: str | None) -> str | None:
        # The pattern accepts 2025-13-45; the backend does not. Catching it here keeps a
        # calendar typo from costing a request against a priced route.
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator("include_domains", "exclude_domains", mode="before")
    @classmethod
    def normalize_domains(cls, value: object) -> object:
        # The backend accepts hostnames only, so a pasted URL is corrected here, not there.
        # Before the length bound, so a list that only exceeds 50 through duplicates passes.
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        for item in value:
            host = str(item).strip().lower().rstrip(".")
            if not host or "/" in host or ":" in host:
                raise ValueError("domain filters must be hostname-only values")
            if host not in normalized:
                normalized.append(host)
        return normalized

    @field_validator("resource_kinds", mode="before")
    @classmethod
    def deduplicate_kinds(cls, value: object) -> object:
        # Runs before the length bound: `--kind paper --kind paper --kind web` is three
        # values and two kinds, and rejecting it for length would be a lie about the input.
        if not isinstance(value, list):
            return value
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def reject_contradictory_filters(self) -> ResearchRunCreateRequest:
        # A domain in both lists can never match, so catch it before spending a request.
        if set(self.include_domains or ()) & set(self.exclude_domains or ()):
            raise ValueError("a domain cannot be both included and excluded")
        return self


class ResearchRunAccepted(BaseModel):
    """The 202 identity returned by start, add, and resume."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: str = Field(alias="encrypted_id")
    run_id: str
    status: ResearchStatus


class ResearchRunStatus(BaseModel):
    """One run's durable progress.

    The backend also sends the thread's internal identifier here. It is deliberately not
    declared, so `extra="ignore"` drops it and no renderer can print an ID that would be
    rejected the moment a user pasted it into `research add`.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    run_id: str
    status: ResearchStatus
    phase: str
    continuation_count: int = Field(ge=0)
    updated_at: datetime


class ResearchThreadSummary(BaseModel):
    """One row of the caller's thread portfolio."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: str = Field(alias="encrypted_id")
    title: str
    run_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    latest_run_id: str | None = None
    latest_run_status: ResearchStatus | None = None
    created_at: datetime
    updated_at: datetime


class ResearchThreadDetail(ResearchThreadSummary):
    """One thread read on its own, which carries two fields a portfolio row omits."""

    latest_run_phase: str | None = None
    favorite: bool = False


class ResearchPortfolioPage(BaseModel):
    """One bounded page of threads and the cursor that continues it."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    threads: list[ResearchThreadSummary]
    next_cursor: str | None = None
