"""Strict contracts shared by the suggestion command and service.

The models define the in-process boundary before provider work begins and the
versioned envelopes emitted afterward. Provider adapters and command rendering
stay outside this module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .attachments import AttachmentBundle

SCHEMA_VERSION = 1
MAX_CONTEXT_CHARS = 5_000_000
MAX_AGENT_MESSAGE_CHARS = 2_000

SUGGESTIONS_RESULT_KIND = "suggestions.result"
SUGGESTIONS_HANDOFF_KIND = "suggestions.handoff"
_FEEDBACK_REASON_SEPARATOR = "\nReason: "


class SuggestionHorizon(StrEnum):
    """When a suggestion should become useful to its caller."""

    NOW = "now"
    NEXT = "next"
    LATER = "later"
    ANY = "any"


class IdeaHorizon(StrEnum):
    """Horizon value stored on one idea; never the ``any`` filter wildcard."""

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
    NEEDS_INPUT = "needs_input"


class StopReason(StrEnum):
    """Why the workflow stopped when it did."""

    COMPLETED = "completed"
    COUNT_SHORTFALL = "count_shortfall"
    ROUND_LIMIT = "round_limit"
    TOKEN_LIMIT = "token_limit"
    TIME_LIMIT = "time_limit"
    PROVIDER_FAILED = "provider_failed"
    DRY_RUN = "dry_run"
    PARENT_MESSAGE = "parent_message"


class SuggestionContextItem(BaseModel):
    """One labeled piece of caller-supplied context with a stable run-local ref."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=4096)
    content: str = Field(min_length=1, max_length=MAX_CONTEXT_CHARS)
    source: str = Field(min_length=1, max_length=512)
    caller_supplied: bool = True


@dataclass(frozen=True, slots=True)
class SuggestionContextPrimitive:
    """SDK context primitive for one exact generator or critic context window."""

    goal: str
    description: str
    items: tuple[SuggestionContextItem, ...] = ()
    selected_categories: str = ""
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
        sections = [f"Goal: {self.goal}", "", "<Selected Categories>"]
        sections.append(self.selected_categories or "No category was selected.")
        sections.extend(("</Selected Categories>", ""))
        for item in self.items:
            sections.extend(
                (
                    f"## [{item.ref}] {item.label} ({item.kind})",
                    f"Source: {item.source}",
                    item.content,
                    "",
                )
            )
        return "\n".join(sections).rstrip()


class FeedbackType(StrEnum):
    """The explicit user reaction stored in project memory."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SuggestionProjectRecord(BaseModel):
    """One catalog entry linking a project key to its memory file."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    memory_file: str = Field(min_length=1, max_length=256)


class SuggestionProjectCatalog(BaseModel):
    """Versioned catalog document containing all project summaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    projects: tuple[SuggestionProjectRecord, ...] = ()


class SuggestionFeedback(BaseModel):
    """One accepted or rejected suggestion recorded by an explicit user reaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    type: FeedbackType
    suggestion: str = Field(min_length=1, max_length=8192)
    reason: str | None = Field(default=None, max_length=8192)
    created_at: str = Field(min_length=1, max_length=64)

    def context_text(self) -> str:
        # The one rendering of a reaction as run context; suggestion_from_context inverts it,
        # so the label and reason separator are defined together and cannot drift apart.
        reason = f"{_FEEDBACK_REASON_SEPARATOR}{self.reason}" if self.reason else ""
        return f"{self.type.value.title()} suggestion: {self.suggestion}{reason}"

    @staticmethod
    def suggestion_from_context(text: str) -> str:
        # Recovers the verbatim suggestion so rejected feedback can suppress a repeated idea.
        body = text.split(": ", 1)[1] if ": " in text else text
        return body.split(_FEEDBACK_REASON_SEPARATOR, 1)[0].strip()


class SuggestionProjectMemory(BaseModel):
    """Versioned per-project feedback document."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    project_key: str = Field(min_length=1, max_length=64)
    feedback: tuple[SuggestionFeedback, ...] = ()


class SuggestionFeedbackCapture(BaseModel):
    """Deterministic instructions a parent agent can use after explicit feedback."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_key: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=1024)
    accept_command: str = Field(min_length=1, max_length=1024)
    reject_command: str = Field(min_length=1, max_length=1024)


class ContextManifestEntry(BaseModel):
    """What the manifest records about one context item without its body."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=512)
    chars: int = Field(ge=0, le=MAX_CONTEXT_CHARS)
    sha256: str = Field(min_length=8, max_length=128)
    status: Literal["included", "truncated", "omitted", "not_supplied"] = "included"


class SuggestionSettings(BaseModel):
    """The one validated settings object passed unchanged through the workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    requested_count: int = Field(ge=2, le=15, default=5)
    categories: tuple[str, ...] = ()
    all_categories: bool = False
    extra_compute: bool = False
    horizon: SuggestionHorizon = SuggestionHorizon.ANY
    rounds: int = Field(ge=1, le=8, default=2)
    max_messages: int = Field(ge=0, le=8, default=2)
    provider: str | None = None
    critic_model: str | None = None
    max_output_tokens: int | None = Field(default=None, gt=0, le=5_000_000)
    max_total_tokens: int | None = Field(default=None, gt=0, le=20_000_000)
    timeout_seconds: int | None = Field(default=None, gt=0, le=86_400)
    dry_run: bool = False

    @model_validator(mode="after")
    def _validate_categories(self) -> SuggestionSettings:
        if self.all_categories and self.categories:
            raise ValueError("all_categories and categories cannot both be selected.")
        return self


class SuggestionRequest(BaseModel):
    """Validated input to one suggestion run, built by the command layer."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    goal: str = Field(min_length=1, max_length=4096)
    context: SuggestionContextPrimitive
    context_manifest: tuple[ContextManifestEntry, ...] = ()
    context_warnings: tuple[str, ...] = ()
    settings: SuggestionSettings
    attachments: AttachmentBundle = Field(default_factory=AttachmentBundle)
    project_key: str | None = Field(default=None, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v4")

    @model_validator(mode="after")
    def _context_goal_matches(self) -> SuggestionRequest:
        if self.goal != self.context.goal:
            raise ValueError("Suggestion request goal must match its context primitive goal.")
        return self

    @property
    def context_items(self) -> tuple[SuggestionContextItem, ...]:
        return self.context.items


class SuggestionDraft(BaseModel):
    """One model-produced candidate before the CLI assigns identity and a handoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    idea_id: str | None = Field(default=None, pattern=r"^idea-\d{3}$")
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
    suggested_actions: tuple[str, ...] = Field(min_length=1, max_length=12)
    decision_points: tuple[str, ...] = Field(default=(), max_length=12)
    considerations: tuple[str, ...] = Field(default=(), min_length=8, max_length=10)
    completion_criteria: str = Field(min_length=1, max_length=1024)
    effort_estimate: str = Field(min_length=1, max_length=256)


class SuggestionCandidateBatch(BaseModel):
    """Structured output requested from the generator for initial and revision turns."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ideas: tuple[SuggestionDraft, ...] = Field(max_length=30)


class SuggestionCriticHandoff(BaseModel):
    """One general review of the whole candidate slate, handed to the generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    handoff: str = Field(
        min_length=1,
        max_length=16384,
        description=(
            "The critic's complete review of the candidate slate, written for the generator "
            "that will refine it. Grade the slate against the general suggestion rubric, name "
            "candidates by identifier where a point concerns them, and cite the context "
            "references behind every factual claim. The generator weighs this handoff with its "
            "own judgment, so explain what is strong, what is weak, and why, rather than "
            "issuing keep, revise, or reject verdicts."
        ),
    )


def _packet(models: tuple[BaseModel, ...]) -> str:
    """Render one typed model tuple as the compact JSON a model window reads."""
    return json.dumps(
        [model.model_dump(mode="json") for model in models],
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class SuggestionEvidence:
    """One supplied record as a model sees it: its stable ref, its kind, its body."""

    ref: str
    kind: str
    content: str


@dataclass(frozen=True, slots=True)
class SuggestionAgentContext:
    """SDK context primitive holding exactly what one workflow stage may read.

    Caller-only data has no field here at all, so a stage cannot place a source
    path, a label, a manifest entry, a setting, or workflow state such as rank,
    revision, or handoff into a model window. Candidates travel as the same
    `SuggestionDraft` contract the generator returns, so no parallel projection
    can drift.
    """

    description: str
    evidence: tuple[SuggestionEvidence, ...] = ()
    selected_categories: str = ""
    candidates: tuple[SuggestionDraft, ...] = ()
    kind: str = field(default="suggestion-context", init=False)
    title: str = field(default="Suggestion Agent Context", init=False)
    metadata: Mapping[str, object] = field(default_factory=dict, init=False)
    primitive_id: str = field(default="suggestion-context:stage", init=False)
    primitive_frozen: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Suggestion agent context description must be a non-empty string.")

    @classmethod
    def for_stage(
        cls,
        context: SuggestionContextPrimitive,
        selected_categories: str,
        candidates: tuple[SuggestionDraft, ...] = (),
    ) -> SuggestionAgentContext:
        """Build one stage window from the caller snapshot without mutating it."""
        return cls(
            description="Stage context holds only evidence, category guidance, and candidates.",
            evidence=tuple(
                SuggestionEvidence(item.ref, item.kind, item.content) for item in context.items
            ),
            selected_categories=selected_categories,
            candidates=candidates,
        )

    def to_context_text(self) -> str:
        # Every stage prompt already states the goal, so this window stays task data only.
        sections = [
            "<Selected Categories>",
            self.selected_categories or "No category was selected.",
            "</Selected Categories>",
            "",
        ]
        for item in self.evidence:
            sections.extend((f"## [{item.ref}] {item.kind}", item.content, ""))
        if self.candidates:
            sections.extend(("<Candidates>", _packet(self.candidates), "</Candidates>"))
        return "\n".join(sections).rstrip()


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
    suggested_actions: tuple[str, ...] = Field(min_length=1, max_length=12)
    decisions_along_way: tuple[str, ...] = Field(default=(), max_length=12)
    considerations: tuple[str, ...] = Field(default=(), min_length=8, max_length=10)
    evidence: tuple[SuggestionHandoffEvidence, ...] = ()
    completion_checks: tuple[str, ...] = Field(min_length=1, max_length=12)
    dependencies: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    authority: Literal["not_granted_by_this_handoff"] = "not_granted_by_this_handoff"
    stop_conditions: tuple[str, ...] = Field(min_length=1)
    return_report: str = Field(min_length=1, max_length=2048)
    execution_prompt: str = Field(min_length=1, max_length=16384)


class SuggestionIdea(BaseModel):
    """One ranked suggestion with its deterministic handoff."""

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
    suggested_actions: tuple[str, ...] = Field(min_length=1, max_length=12)
    decision_points: tuple[str, ...] = Field(default=(), max_length=12)
    considerations: tuple[str, ...] = Field(default=(), min_length=8, max_length=10)
    completion_criteria: str = Field(min_length=1, max_length=1024)
    effort_estimate: str = Field(min_length=1, max_length=256)
    handoff: SuggestionHandoff

    def to_draft(self) -> SuggestionDraft:
        """Project this reviewed idea back to the candidate contract agents reason over."""
        # Identity stays as idea_id; CLI-owned workflow fields stay behind.
        values = self.model_dump(exclude={"id", "revision", "rank", "handoff"})
        return SuggestionDraft.model_validate({**values, "idea_id": self.id})


class SuggestionResult(BaseModel):
    """Whole validated outcome of one run, including shortfalls and usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str = Field(min_length=1, max_length=64)
    status: RunStatus = RunStatus.COMPLETE
    goal: str = Field(min_length=1, max_length=4096)
    project_key: str | None = Field(default=None, max_length=64)
    requested_count: int = Field(ge=2, le=15)
    returned_count: int = Field(ge=0, le=15)
    settings: SuggestionSettings
    context_manifest: tuple[ContextManifestEntry, ...] = ()
    ideas: tuple[SuggestionIdea, ...] = ()
    category_coverage: dict[str, int] = Field(default_factory=dict)
    missing_context: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: dict[str, int] = Field(default_factory=dict)
    stop_reason: StopReason = StopReason.COMPLETED
    parent_message: str | None = Field(default=None, max_length=MAX_AGENT_MESSAGE_CHARS)
    feedback_capture: SuggestionFeedbackCapture | None = None
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v4")


__all__ = [
    "ContextManifestEntry",
    "FeedbackType",
    "IdeaHorizon",
    "IdeaReadiness",
    "IdeaRelationship",
    "MAX_AGENT_MESSAGE_CHARS",
    "MAX_CONTEXT_CHARS",
    "RunStatus",
    "SCHEMA_VERSION",
    "SUGGESTIONS_HANDOFF_KIND",
    "SUGGESTIONS_RESULT_KIND",
    "StopReason",
    "SuggestionAgentContext",
    "SuggestionCandidateBatch",
    "SuggestionContextItem",
    "SuggestionContextPrimitive",
    "SuggestionCriticHandoff",
    "SuggestionDraft",
    "SuggestionFeedback",
    "SuggestionFeedbackCapture",
    "SuggestionEvidence",
    "SuggestionHandoff",
    "SuggestionHandoffEvidence",
    "SuggestionHorizon",
    "SuggestionIdea",
    "SuggestionProjectCatalog",
    "SuggestionProjectMemory",
    "SuggestionProjectRecord",
    "SuggestionRequest",
    "SuggestionResult",
    "SuggestionSettings",
]
