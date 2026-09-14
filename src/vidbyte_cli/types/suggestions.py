"""Versioned contracts for the suggestion (next-action) agent.

The CLI owns these shapes so commands, services, and output rendering share one
source of truth. All models are frozen and forbid extras, so contract drift fails
before a model call rather than after. No transport or provider code lives here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

SUGGESTIONS_RESULT_KIND = "suggestions.result"
SUGGESTIONS_HANDOFF_KIND = "suggestions.handoff"


class SuggestionHorizon(StrEnum):
    """When a suggestion should become useful to its caller."""

    NOW = "now"
    NEXT = "next"
    LATER = "later"
    ANY = "any"


class IdeaHorizon(StrEnum):
    """Horizon value stored on one idea; never the `any` filter wildcard."""

    NOW = "now"
    NEXT = "next"
    LATER = "later"


class IdeaRelationship(StrEnum):
    """How an idea relates to the caller's stated goal."""

    DIRECT = "direct"
    ALTERNATIVE = "alternative"
    ADJACENT = "adjacent"
    EXPLORATORY = "exploratory"


class IdeaReadiness(StrEnum):
    """What must happen before an executor can start the idea."""

    READY = "ready"
    NEEDS_EVIDENCE = "needs_evidence"
    NEEDS_DECISION = "needs_decision"
    BLOCKED = "blocked"


class RunStatus(StrEnum):
    """Terminal state of one suggestion run."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    NO_SUGGESTIONS = "no_suggestions"


class StopReason(StrEnum):
    """Why the workflow stopped when it did."""

    COMPLETED = "completed"
    COUNT_SHORTFALL = "count_shortfall"
    ROUND_LIMIT = "round_limit"
    TOKEN_LIMIT = "token_limit"
    TIME_LIMIT = "time_limit"
    PROVIDER_FAILED = "provider_failed"
    DRY_RUN = "dry_run"


class SuggestionContextItem(BaseModel):
    """One labeled piece of caller-supplied context with a stable run-local ref."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=256)
    description: str = Field(
        min_length=1,
        max_length=2048,
        default="This caller-supplied record provides context for suggestion reasoning.",
    )
    content: str = Field(min_length=1, max_length=65536)
    source: str = Field(min_length=1, max_length=512)
    caller_supplied: bool = True


@dataclass(frozen=True, slots=True)
class SuggestionContextPrimitive:
    """SDK-compatible context primitive containing one complete suggestion snapshot."""

    goal: str
    description: str
    items: tuple[SuggestionContextItem, ...] = ()
    kind: str = field(default="suggestion-context", init=False)
    title: str = field(default="Suggestion Agent Context", init=False)
    metadata: Mapping[str, object] = field(default_factory=dict)
    primitive_id: str = field(default="suggestion-context:request", init=False)
    primitive_frozen: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("Suggestion context goal must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Suggestion context description must be a non-empty string.")
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, SuggestionContextItem) for item in self.items
        ):
            raise TypeError("Suggestion context items must be a tuple of SuggestionContextItem.")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("Suggestion context metadata must be a mapping.")

    def to_context_text(self) -> str:
        sections = [self.description, "", f"Goal: {self.goal}"]
        for item in self.items:
            sections.extend(
                (
                    "",
                    f"## [{item.ref}] {item.label} ({item.kind})",
                    item.description,
                    f"Source: {item.source}",
                    item.content,
                )
            )
        return "\n".join(sections)


class ContextManifestEntry(BaseModel):
    """What the manifest records about one context item without its body."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=512)
    chars: int = Field(ge=0)
    sha256: str = Field(min_length=8, max_length=128)
    status: Literal["included", "truncated", "omitted", "not_supplied"] = "included"


class SuggestionSettings(BaseModel):
    """Resolved generation controls for one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    requested_count: int = Field(ge=1, le=20, default=5)
    categories: tuple[str, ...] = ()
    all_categories: bool = False
    horizon: SuggestionHorizon = SuggestionHorizon.ANY
    rounds: int = Field(ge=1, le=3, default=2)
    provider: str | None = None
    model: str | None = None
    critic_model: str | None = None
    max_output_tokens: int | None = None
    max_total_tokens: int | None = None
    timeout_seconds: int | None = None
    dry_run: bool = False


class SuggestionRequest(BaseModel):
    """Validated input to one suggestion run, built by the command layer."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    goal: str = Field(min_length=1, max_length=4096)
    context: SuggestionContextPrimitive
    settings: SuggestionSettings
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v1")

    @model_validator(mode="after")
    def _context_goal_matches(self) -> SuggestionRequest:
        if self.goal != self.context.goal:
            raise ValueError("Suggestion request goal must match its context primitive goal.")
        return self

    @property
    def context_items(self) -> tuple[SuggestionContextItem, ...]:
        return self.context.items


class SuggestionHandoffEvidence(BaseModel):
    """One context record embedded in a final action handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=4096)
    relevance: str = Field(min_length=1, max_length=1024)


class SuggestionHandoff(BaseModel):
    """Action-centered packet for evaluating and executing one selected idea."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    handoff_version: Literal[1] = 1
    idea_id: str = Field(min_length=1, max_length=64)
    idea_revision: int = Field(ge=1)
    original_goal: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1, max_length=2048)
    suggested_actions: tuple[str, ...] = Field(min_length=1)
    decisions_along_way: tuple[str, ...] = ()
    considerations: tuple[str, ...] = ()
    evidence: tuple[SuggestionHandoffEvidence, ...] = ()
    completion_checks: tuple[str, ...] = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    authority: Literal["not_granted_by_this_handoff"] = "not_granted_by_this_handoff"
    stop_conditions: tuple[str, ...] = Field(min_length=1)
    return_report: str = Field(min_length=1, max_length=2048)
    execution_prompt: str = Field(min_length=1, max_length=16384)


class SuggestionIdea(BaseModel):
    """One ranked suggestion with its review trail and deterministic handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^idea-\d{3}$")
    revision: int = Field(ge=1)
    rank: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1, max_length=2048)
    primary_category: str = Field(min_length=1, max_length=64)
    secondary_categories: tuple[str, ...] = ()
    horizon: IdeaHorizon = IdeaHorizon.NEXT
    relationship: IdeaRelationship = IdeaRelationship.DIRECT
    readiness: IdeaReadiness = IdeaReadiness.READY
    why_now: str = Field(min_length=1, max_length=1024)
    expected_benefit: str = Field(min_length=1, max_length=1024)
    evidence_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    alternative_to: tuple[str, ...] = ()
    first_action: str = Field(min_length=1, max_length=1024)
    suggested_actions: tuple[str, ...] = Field(min_length=1)
    decision_points: tuple[str, ...] = ()
    considerations: tuple[str, ...] = ()
    completion_criteria: str = Field(min_length=1, max_length=1024)
    effort_estimate: str = Field(min_length=1, max_length=256)
    review_summary: str = Field(min_length=1, max_length=1024)
    handoff: SuggestionHandoff


class SuggestionResult(BaseModel):
    """Whole validated outcome of one run, including shortfalls and usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str = Field(min_length=1, max_length=64)
    status: RunStatus = RunStatus.COMPLETE
    goal: str = Field(min_length=1, max_length=4096)
    requested_count: int = Field(ge=1, le=20)
    returned_count: int = Field(ge=0, le=20)
    settings: SuggestionSettings
    context_manifest: tuple[ContextManifestEntry, ...] = ()
    ideas: tuple[SuggestionIdea, ...] = ()
    category_coverage: dict[str, int] = Field(default_factory=dict)
    missing_context: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: dict[str, int] = Field(default_factory=dict)
    stop_reason: StopReason = StopReason.COMPLETED
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v1")
