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
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .attachments import AttachmentBundle

SCHEMA_VERSION = 1
MAX_CONTEXT_CHARS = 5_000_000
MAX_AGENT_MESSAGE_CHARS = 2_000

SUGGESTIONS_RESULT_KIND = "suggestions.result"
SUGGESTIONS_HANDOFF_KIND = "suggestions.handoff"


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


class CriticObservationKind(StrEnum):
    """The kind of useful signal one whole-slate observation carries."""

    STRENGTH = "strength"
    EVIDENCE = "evidence"
    CONSTRAINT = "constraint"
    REDUNDANCY = "redundancy"
    COVERAGE = "coverage"
    FEASIBILITY = "feasibility"
    ACTIONABILITY = "actionability"
    TRADEOFF = "tradeoff"
    RISK = "risk"


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
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v3")

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


class SuggestionCriticObservation(BaseModel):
    """One evidence-linked observation about any part of the candidate slate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: CriticObservationKind = Field(
        description=(
            "The observation's decision-relevant subject. Use strength for something worth "
            "preserving, evidence or constraint for supplied-context findings, redundancy or "
            "coverage for relationships across the slate, feasibility or actionability for "
            "execution concerns, and tradeoff or risk for costs and downside."
        )
    )
    candidate_ids: tuple[str, ...] = Field(
        default=(),
        max_length=30,
        description=(
            "Zero to thirty candidate identifiers affected by this observation. Use several IDs "
            "when the signal concerns overlap or balance across candidates, one for a local point, "
            "and none when the observation concerns the slate as a whole. Every supplied ID must "
            "come from the reviewed candidate packet."
        ),
    )
    evidence_refs: tuple[str, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Zero to twelve stable context references that support the observation. Cite every "
            "relevant supplied record when the point depends on caller evidence, and leave this "
            "empty only for relationships visible directly in the candidates or for an explicit "
            "uncertainty."
        ),
    )
    signal: str = Field(
        min_length=1,
        max_length=2048,
        description=(
            "The concrete pattern, strength, defect, conflict, gap, or tradeoff the critic found. "
            "State what is visible in the supplied candidates and context without issuing a keep, "
            "revise, or reject command."
        ),
    )
    implication: str = Field(
        min_length=1,
        max_length=2048,
        description=(
            "Why the signal matters to the quality or usefulness of the complete slate. Connect "
            "the observation to the caller's goal and name the likely consequence without "
            "pretending uncertainty has been resolved."
        ),
    )
    possible_response: str = Field(
        default="",
        max_length=2048,
        description=(
            "One evidence-supported way the generator could respond, left empty when the useful "
            "signal needs no change or the supplied material does not establish a correction. "
            "This is an option for the generator to weigh, never a field-level repair order."
        ),
    )


class SuggestionCriticContext(BaseModel):
    """One bounded whole-slate review returned by an independent critic."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    overall_assessment: str = Field(
        min_length=1,
        max_length=4096,
        description=(
            "A concise account of how well the candidate slate serves the stated goal as a whole. "
            "Describe its strongest direction, its most consequential weakness, and the balance of "
            "evidence, feasibility, distinctness, and risk without deciding which candidates the "
            "generator must keep or remove."
        ),
    )
    strengths_to_preserve: tuple[str, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Up to twelve useful properties, mechanisms, distinctions, or evidence connections "
            "that should not be lost casually during refinement. These are slate-level signals, "
            "not frozen fields, and the generator remains free to preserve their value in a "
            "different candidate shape."
        ),
    )
    observations: tuple[SuggestionCriticObservation, ...] = Field(
        default=(),
        max_length=20,
        description=(
            "Up to twenty high-signal observations spanning individual candidates or the whole "
            "slate. Prefer fewer consequential observations over a checklist entry for every "
            "candidate, combine related evidence once, and use candidate identifiers only as "
            "anchors for the generator's judgment."
        ),
    )
    coverage_gaps: tuple[str, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Up to twelve missing perspectives, mechanisms, horizons, or decision needs that make "
            "the slate less useful. Name only gaps supported by the selected categories and caller "
            "context, and do not turn this collection into a list of new candidate drafts."
        ),
    )
    uncertainties: tuple[str, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Up to twelve questions the supplied material cannot settle but the generator should "
            "keep visible. Distinguish missing evidence from contradiction and avoid filling an "
            "unknown with a confident recommendation."
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


Drafts = tuple[SuggestionDraft, ...]


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
    candidates: Drafts = ()
    kind: str = field(default="suggestion-context", init=False)
    title: str = field(default="Suggestion Agent Context", init=False)
    metadata: Mapping[str, object] = field(default_factory=dict, init=False)
    primitive_id: str = field(default="suggestion-context:stage", init=False)
    primitive_frozen: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Suggestion agent context description must be a non-empty string.")

    @classmethod
    def for_stage(cls, src: SuggestionContextPrimitive, cats: str, drafts: Drafts = ()) -> Self:
        # Builds one stage window from the caller snapshot without mutating it.
        return cls(
            description="Stage context holds only evidence, category guidance, and candidates.",
            evidence=tuple(
                SuggestionEvidence(item.ref, item.kind, item.content) for item in src.items
            ),
            selected_categories=cats,
            candidates=drafts,
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


@dataclass(frozen=True, slots=True)
class SuggestionCriticContextPrimitive:
    """One replaceable whole-slate review placed after the generator's turn input."""

    context: SuggestionCriticContext
    messages: tuple[str, ...] = ()
    kind: str = field(default="suggestion-critic-context", init=False)
    title: str = field(default="Independent Critic Signal Context", init=False)
    metadata: Mapping[str, object] = field(default_factory=dict, init=False)
    primitive_id: str = field(default="suggestion-critic:latest", init=False)
    primitive_frozen: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        # Rejects loose mappings so only the validated critic artifact enters context.
        if not isinstance(self.context, SuggestionCriticContext):
            raise TypeError("Critic context primitive requires SuggestionCriticContext.")
        if (
            not isinstance(self.messages, tuple)
            or len(self.messages) > 4
            or any(
                not isinstance(message, str)
                or not message.strip()
                or len(message.strip()) > MAX_AGENT_MESSAGE_CHARS
                for message in self.messages
            )
        ):
            raise TypeError("Critic context messages must be bounded non-empty strings.")

    def to_context_text(self) -> str:
        # Renders one readable block while preserving typed references and review order.
        sections = [
            "<Critic Signal Context>",
            "## Overall assessment",
            self.context.overall_assessment,
            "",
            "## Strengths to preserve",
            *self._lines(self.context.strengths_to_preserve),
            "",
            "## Observations",
            *self._observations(),
            "",
            "## Coverage gaps",
            *self._lines(self.context.coverage_gaps),
            "",
            "## Uncertainties",
            *self._lines(self.context.uncertainties),
            "",
            "## Messages from critic",
            *self._lines(self.messages),
            "</Critic Signal Context>",
        ]
        return "\n".join(sections)

    def _observations(self) -> list[str]:
        # Keeps each observation together so its anchors and implication read as one signal.
        if not self.context.observations:
            return ["- none supplied"]
        rendered: list[str] = []
        for item in self.context.observations:
            candidates = ", ".join(item.candidate_ids) or "whole slate"
            evidence = ", ".join(item.evidence_refs) or "candidate artifact"
            rendered.append(
                f"- [{item.kind.value}] {item.signal} Candidates: {candidates}. "
                f"Evidence: {evidence}. Implication: {item.implication}"
            )
            if item.possible_response:
                rendered.append(f"  Possible response: {item.possible_response}")
        return rendered

    def _lines(self, values: tuple[str, ...]) -> list[str]:
        # Makes absent optional sections explicit without manufacturing review content.
        return [f"- {value}" for value in values] or ["- none supplied"]


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
    """One generator-owned ranked suggestion with its deterministic handoff."""

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
        # Projects one idea back to the candidate contract while retaining its stable ID.
        values = self.model_dump(exclude={"id", "revision", "rank", "handoff"})
        return SuggestionDraft.model_validate({**values, "idea_id": self.id})


class SuggestionResult(BaseModel):
    """Whole validated outcome of one run, including shortfalls and usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str = Field(min_length=1, max_length=64)
    status: RunStatus = RunStatus.COMPLETE
    goal: str = Field(min_length=1, max_length=4096)
    requested_count: int = Field(ge=2, le=15)
    returned_count: int = Field(ge=0, le=15)
    settings: SuggestionSettings
    context_manifest: tuple[ContextManifestEntry, ...] = ()
    ideas: tuple[SuggestionIdea, ...] = ()
    critic_contexts: tuple[SuggestionCriticContext, ...] = ()
    agent_messages: tuple[str, ...] = Field(default=(), max_length=4)
    category_coverage: dict[str, int] = Field(default_factory=dict)
    missing_context: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: dict[str, int] = Field(default_factory=dict)
    stop_reason: StopReason = StopReason.COMPLETED
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v3")


__all__ = [
    "ContextManifestEntry",
    "CriticObservationKind",
    "IdeaHorizon",
    "IdeaReadiness",
    "IdeaRelationship",
    "MAX_CONTEXT_CHARS",
    "MAX_AGENT_MESSAGE_CHARS",
    "RunStatus",
    "SCHEMA_VERSION",
    "SUGGESTIONS_HANDOFF_KIND",
    "SUGGESTIONS_RESULT_KIND",
    "StopReason",
    "SuggestionAgentContext",
    "SuggestionCandidateBatch",
    "SuggestionContextItem",
    "SuggestionContextPrimitive",
    "SuggestionCriticContext",
    "SuggestionCriticContextPrimitive",
    "SuggestionCriticObservation",
    "SuggestionDraft",
    "SuggestionEvidence",
    "SuggestionHandoff",
    "SuggestionHandoffEvidence",
    "SuggestionHorizon",
    "SuggestionIdea",
    "SuggestionRequest",
    "SuggestionResult",
    "SuggestionSettings",
]
