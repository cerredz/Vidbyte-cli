"""FILE: src/vidbyte_cli/features/research/infrastructure/wire.py

PURPOSE: Defines research-only HTTP request/response DTOs and explicit mappings to the
backend-neutral domain.

ROLE IN CODEBASE: ApiResearchGateway decodes only these models. Domain services never see
the backend's `paper`/`web` vocabulary or transport-only fields.

ARCHITECTURE NOTE: Mutation request fields match Vidbyte PR #284 exactly except
`provider_keys`, which is deliberately unavailable through the CLI. Forward read DTOs
ignore additive server fields while request DTOs forbid unknown client fields.

TESTS: No feature tests are added under the approved no-tests workflow. Mock-transport
verification checks exact serialized mutations and every mapper.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ..domain import (
    ResearchArtifact,
    ResearchRun,
    ResearchRunAccepted,
    ResearchRunRequest,
    ResearchSize,
    ResearchSource,
    ResearchStatus,
    ResearchThread,
    ResourceKind,
)

WireResearchKind = Literal["paper", "web"]
_WireItem = TypeVar("_WireItem", bound=BaseModel)

_TO_WIRE_KIND: dict[ResourceKind, WireResearchKind] = {
    ResourceKind.RESEARCH_PAPER: "paper",
    ResourceKind.WEB_PAGE: "web",
}
_TO_DOMAIN_KIND = {
    "paper": ResourceKind.RESEARCH_PAPER,
    "web": ResourceKind.WEB_PAGE,
}


class ApiResearchRunCreateRequest(BaseModel):
    """Exact admitted-run request without the backend-only provider-key escape hatch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str
    request_schema_version: Literal[1] = 1
    size: ResearchSize
    target_sources: int | None = None
    search_calls: int | None = None
    resource_kinds: list[WireResearchKind]
    include_domains: list[str]
    exclude_domains: list[str]
    published_after: str | None = None
    language: str

    @classmethod
    def from_domain(cls, request: ResearchRunRequest) -> ApiResearchRunCreateRequest:
        kinds = request.resource_kinds or list(ResourceKind)
        return cls(
            prompt=request.prompt,
            request_schema_version=request.request_schema_version,
            size=request.size,
            target_sources=request.target_sources,
            search_calls=request.search_calls,
            resource_kinds=[_TO_WIRE_KIND[item] for item in kinds],
            include_domains=request.include_domains,
            exclude_domains=request.exclude_domains,
            published_after=(
                request.published_after.isoformat() if request.published_after is not None else None
            ),
            language=request.language or "en",
        )


class ApiResearchRunAccepted(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: str
    run_id: str
    status: ResearchStatus = ResearchStatus.ACCEPTED

    def to_domain(self) -> ResearchRunAccepted:
        return ResearchRunAccepted.model_validate(self.model_dump())


class ApiResearchRun(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: str
    run_id: str
    status: ResearchStatus
    target_sources: int | None = Field(default=None, ge=0)
    discovered_sources: int = Field(default=0, ge=0)
    generated_artifacts: int = Field(default=0, ge=0)
    message: str | None = None
    disclaimer: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_domain(self) -> ResearchRun:
        return ResearchRun(
            thread_id=self.thread_id,
            run_id=self.run_id,
            status=self.status,
            requested_sources=self.target_sources,
            discovered_sources=self.discovered_sources,
            generated_artifacts=self.generated_artifacts,
            message=self.message or self.disclaimer,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ApiResearchThread(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    thread_id: str
    title: str | None = None
    run_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    artifact_count: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_domain(self) -> ResearchThread:
        return ResearchThread.model_validate(self.model_dump())


class ApiResearchSource(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    source_id: str
    thread_id: str
    url: str
    title: str
    resource_kind: WireResearchKind | None = None
    favorite: bool = False
    deleted_at: datetime | None = None

    def to_domain(self) -> ResearchSource:
        return ResearchSource(
            source_id=self.source_id,
            thread_id=self.thread_id,
            url=self.url,
            title=self.title,
            resource_kind=(
                _TO_DOMAIN_KIND[self.resource_kind] if self.resource_kind is not None else None
            ),
            favorite=self.favorite,
            deleted=self.deleted_at is not None,
        )


class ApiResearchArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    artifact_id: str
    thread_id: str
    source_id: str | None = None
    title: str
    summary: str | None = None
    relevance: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_url: str | None = None
    content: str | None = None
    full_content: str | None = None
    favorite: bool = False
    deleted_at: datetime | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    def to_domain(self) -> ResearchArtifact:
        metadata = dict(self.metadata)
        if self.evidence:
            metadata["evidence"] = cast(list[JsonValue], self.evidence)
        if self.limitations:
            metadata["limitations"] = cast(list[JsonValue], self.limitations)
        if self.content is not None:
            metadata["content"] = self.content
        if self.full_content is not None:
            metadata["full_content"] = self.full_content
        return ResearchArtifact(
            artifact_id=self.artifact_id,
            thread_id=self.thread_id,
            source_id=self.source_id,
            title=self.title,
            summary=self.summary,
            relevance=self.relevance,
            recommendations=self.recommendations,
            source_url=self.source_url,
            favorite=self.favorite,
            metadata=metadata,
        )


class ApiResearchPage(BaseModel, Generic[_WireItem]):
    model_config = ConfigDict(extra="ignore", frozen=True)

    items: list[_WireItem] = Field(default_factory=list)
    next_cursor: str | None = None
