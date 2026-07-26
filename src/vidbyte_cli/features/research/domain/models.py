"""FILE: src/vidbyte_cli/features/research/domain/models.py

PURPOSE: Defines strict research request, persistent resource, pagination, capability, and
export vocabulary without Click or HTTPX.

ROLE IN CODEBASE: Application services and the final gateway adapter exchange only these
models. Identifiers remain opaque strings and provider credentials are intentionally absent.

ARCHITECTURE NOTE: Request normalization deduplicates domains/resource kinds, rejects
contradictory filters, and accepts cleartext HTTP sources only as returned resource URLs.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Generic, Literal, TypeVar
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

OpaqueId = str
TItem = TypeVar("TItem")


class ResearchStatus(StrEnum):
    ADMITTING = "admitting"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CREDIT_EXHAUSTED = "credit_exhausted"


class ResearchSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ResourceKind(StrEnum):
    RESEARCH_PAPER = "research_paper"
    WEB_PAGE = "web_page"


def _normalize_domains(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        candidate = value.strip().lower().rstrip(".")
        if "://" in candidate:
            parsed = urlsplit(candidate)
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("domain filters cannot contain paths, queries, or fragments")
            candidate = parsed.hostname or ""
        if not re.fullmatch(r"[a-z0-9.-]{1,253}", candidate) or ".." in candidate:
            raise ValueError("invalid domain filter")
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


class ResearchRunRequest(BaseModel):
    """Version-one backend-neutral research mutation input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_schema_version: Literal[1] = 1
    prompt: str = Field(min_length=1, max_length=20_000)
    size: ResearchSize = ResearchSize.SMALL
    target_sources: int | None = Field(default=None, ge=1, le=1_000)
    search_calls: int | None = Field(default=None, ge=1, le=100)
    resource_kinds: list[ResourceKind] = Field(default_factory=list, max_length=10)
    include_domains: list[str] = Field(default_factory=list, max_length=100)
    exclude_domains: list[str] = Field(default_factory=list, max_length=100)
    published_after: date | None = None
    language: str | None = Field(default=None, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})?$")

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt cannot be blank")
        return normalized

    @field_validator("include_domains", "exclude_domains")
    @classmethod
    def normalize_domains(cls, value: list[str]) -> list[str]:
        return _normalize_domains(value)

    @field_validator("resource_kinds")
    @classmethod
    def deduplicate_kinds(cls, value: list[ResourceKind]) -> list[ResourceKind]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def reject_conflicting_domains(self) -> ResearchRunRequest:
        overlap = set(self.include_domains) & set(self.exclude_domains)
        if overlap:
            raise ValueError("a domain cannot be both included and excluded")
        if self.published_after is not None and self.published_after > date.today():
            raise ValueError("published_after cannot be in the future")
        return self


class ResearchRunAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: OpaqueId = Field(min_length=1, max_length=200)
    run_id: OpaqueId = Field(min_length=1, max_length=200)
    status: ResearchStatus


class ResearchRun(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: OpaqueId = Field(min_length=1, max_length=200)
    run_id: OpaqueId = Field(min_length=1, max_length=200)
    status: ResearchStatus
    prompt: str | None = Field(default=None, max_length=20_000)
    requested_sources: int | None = Field(default=None, ge=0)
    discovered_sources: int = Field(default=0, ge=0)
    generated_artifacts: int = Field(default=0, ge=0)
    message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResearchThread(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: OpaqueId = Field(min_length=1, max_length=200)
    title: str | None = None
    run_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    source_id: OpaqueId = Field(min_length=1, max_length=200)
    thread_id: OpaqueId = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=4_096)
    title: str = Field(min_length=1, max_length=1_000)
    resource_kind: ResourceKind | None = None
    favorite: bool = False
    deleted: bool = False


class ResearchArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    artifact_id: OpaqueId = Field(min_length=1, max_length=200)
    thread_id: OpaqueId = Field(min_length=1, max_length=200)
    source_id: OpaqueId | None = None
    title: str = Field(min_length=1, max_length=1_000)
    summary: str | None = None
    relevance: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    source_url: str | None = None
    favorite: bool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ResearchCapabilities(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    resource_kinds: list[ResourceKind] = Field(default_factory=list)
    export_providers: list[str] = Field(default_factory=list)
    maximum_target_sources: int | None = Field(default=None, ge=1)
    maximum_search_calls: int | None = Field(default=None, ge=1)


class Page(BaseModel, Generic[TItem]):
    model_config = ConfigDict(extra="ignore", frozen=True)

    items: list[TItem] = Field(default_factory=list)
    next_cursor: str | None = None


class ExportScope(StrEnum):
    ARTIFACTS = "artifacts"
    THREAD = "thread"
    PORTFOLIO = "portfolio"


class ResearchExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    scope: ExportScope
    artifact_ids: list[OpaqueId] = Field(default_factory=list, max_length=500)
    thread_id: OpaqueId | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_scope(self) -> ResearchExportRequest:
        if self.scope is ExportScope.ARTIFACTS and not self.artifact_ids:
            raise ValueError("artifact export requires at least one artifact ID")
        if self.scope is ExportScope.THREAD and self.thread_id is None:
            raise ValueError("thread export requires a thread ID")
        if self.scope is ExportScope.PORTFOLIO and (self.artifact_ids or self.thread_id):
            raise ValueError("portfolio export cannot include artifact or thread IDs")
        return self


class ResearchExport(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    export_id: OpaqueId = Field(min_length=1, max_length=200)
    provider: str
    scope: ExportScope
    status: str
    destination_url: str | None = None
    created_at: datetime | None = None
