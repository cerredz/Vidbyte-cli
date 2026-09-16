"""Strict contracts shared by the suggestion command and service.

The models define the in-process boundary before provider work begins and the
versioned envelopes emitted afterward. Provider adapters and command rendering
stay outside this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .attachments import AttachmentBundle

SCHEMA_VERSION = 1
MAX_CONTEXT_CHARS = 5_000_000

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


class StopReason(StrEnum):
    """Why the workflow stopped when it did."""

    COMPLETED = "completed"
    COUNT_SHORTFALL = "count_shortfall"
    ROUND_LIMIT = "round_limit"
    TOKEN_LIMIT = "token_limit"
    TIME_LIMIT = "time_limit"
    PROVIDER_FAILED = "provider_failed"
    DRY_RUN = "dry_run"


class CritiqueVerdict(StrEnum):
    """The critic's control signal for one candidate."""

    KEEP = "keep"
    REVISE = "revise"
    REJECT = "reject"


class CritiqueConfidence(StrEnum):
    """How certain the critic is about its verdict."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CritiqueEvidenceCheck(StrEnum):
    """Whether candidate claims are grounded in the supplied context."""

    SUPPORTED = "supported"
    MISSING = "missing"
    CONTRADICTS = "contradicts"


class CritiqueConstraint(StrEnum):
    """The hard context boundary, if any, that a candidate hits."""

    FORBIDDEN = "forbidden"
    COMPLETED = "completed"
    IN_PROGRESS = "in-progress"
    NONE = "none"


class CritiqueSignalLevel(StrEnum):
    """Ordinal quality signal without pretending to be a precise score."""

    EXCEPTIONAL = "exceptional"
    STRONG = "strong"
    ADEQUATE = "adequate"
    MARGINAL = "marginal"
    WEAK = "weak"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class CritiqueRiskLevel(StrEnum):
    """Estimated downside signal kept separate from quality dimensions."""

    NEGLIGIBLE = "negligible"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class CritiqueIssueSeverity(StrEnum):
    """How urgently one traceable issue should affect a decision."""

    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"
    NOTE = "note"
    INFO = "info"


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
    candidate_handoffs: str = ""
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
        if self.candidate_handoffs:
            sections.extend(
                (
                    "<Candidate Handoffs>",
                    self.candidate_handoffs,
                    "</Candidate Handoffs>",
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
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v2")

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


class SuggestionCritiqueSignals(BaseModel):
    """Multidimensional observations returned alongside one critic verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    goal_alignment: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How directly the candidate advances the caller's stated goal. "
            "Use exceptional when the candidate is the obvious next move, adequate when "
            "it helps without being central, and weak or absent when the link is thin "
            "or missing. Use unknown when the supplied context says too little to judge."
        ),
    )
    category_fit: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How well the candidate matches its claimed primary category. "
            "Use exceptional when the category definition describes the candidate "
            "exactly, adequate when it fits with minor stretching, and weak when the "
            "label feels borrowed. Use unknown when no category taxonomy was supplied."
        ),
    )
    evidence_grounding: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How firmly the candidate's claims rest on the supplied evidence. "
            "Use exceptional when every material claim cites a supporting reference, "
            "adequate when the core claims hold with minor gaps, and weak when key "
            "claims float free. Use unknown when no evidence was supplied to check."
        ),
    )
    actionability: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How concretely another agent could start executing the candidate. "
            "Use exceptional when the first action names an unambiguous move, adequate "
            "when the path is clear but needs routine clarification, and weak when the "
            "candidate reads as an aspiration. Use unknown when executability cannot "
            "be judged from the supplied context."
        ),
    )
    feasibility: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "Whether the candidate can realistically be done with available means. "
            "Use exceptional when dependencies exist and effort fits the horizon, "
            "adequate when it is plausible with stated assumptions, and weak when it "
            "needs resources the context never shows. Use unknown when feasibility "
            "depends on facts outside the supplied context."
        ),
    )
    internal_coherence: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "Whether the candidate's own parts agree with one another. "
            "Use exceptional when actions, decision points, considerations, "
            "dependencies, and completion criteria tell one story, adequate when they "
            "mostly align, and weak when steps contradict the stated outcome. Use "
            "unknown when the candidate is too thin to check for agreement."
        ),
    )
    distinctness: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How much the candidate adds beyond the other candidates in the batch. "
            "Use exceptional when it opens a direction nothing else covers, adequate "
            "when it overlaps but keeps its own angle, and weak when it restates a "
            "sibling. Use unknown when the rest of the batch is not visible."
        ),
    )
    constraint_compliance: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How cleanly the candidate respects forbidden, completed, and in-progress "
            "boundaries. Use exceptional when it steers visibly clear, adequate when "
            "no boundary is touched, and weak when it brushes against one without a "
            "direct hit. Use unknown when no constraint boundaries were supplied."
        ),
    )
    expected_impact: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How much progress the candidate promises if it succeeds. "
            "Use exceptional when success would move the goal materially, adequate "
            "when it earns a solid incremental gain, and weak when the payoff is "
            "marginal even on success. Use unknown when the payoff cannot be sized "
            "from the supplied context."
        ),
    )
    effort_proportionality: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "Whether the candidate's cost fits its promised payoff. "
            "Use exceptional when the gain clearly outweighs the effort, adequate "
            "when cost and payoff balance, and weak when the effort dwarfs the "
            "return. Use unknown when effort or payoff cannot be sized from the "
            "supplied context."
        ),
    )
    time_to_value: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How quickly the candidate pays off relative to its horizon. "
            "Use exceptional when value lands promptly, adequate when the wait "
            "matches the horizon, and weak when the payoff arrives far later than "
            "the framing implies. Use unknown when timing cannot be judged from the "
            "supplied context."
        ),
    )
    reversibility: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How easily the candidate's effects can be undone if it disappoints. "
            "Use exceptional when every step is cheaply reversible, adequate when "
            "the commitment is bounded, and weak when it burns bridges or spends "
            "irreversible budget. Use unknown when reversibility cannot be judged "
            "from the supplied context."
        ),
    )
    information_gain: CritiqueSignalLevel = Field(
        default=CritiqueSignalLevel.UNKNOWN,
        description=(
            "How much the candidate teaches even if it does not fully succeed. "
            "Use exceptional when the attempt resolves a key uncertainty, adequate "
            "when it yields useful partial evidence, and weak when failure leaves "
            "nothing behind. Use unknown when the learning value cannot be judged "
            "from the supplied context."
        ),
    )
    risk: CritiqueRiskLevel = Field(
        default=CritiqueRiskLevel.UNKNOWN,
        description=(
            "The estimated downside of attempting the candidate, kept separate from "
            "its quality signals. Use negligible when failure costs almost nothing, "
            "moderate when failure wastes real effort, and critical when failure "
            "harms the goal itself. Use unknown when the downside cannot be sized "
            "from the supplied context."
        ),
    )


class SuggestionCritiqueIssue(BaseModel):
    """One evidence-linked defect or useful observation in a critic packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description=(
            "Stable snake-case identifier for the kind of issue, such as "
            "unsupported_claim or duplicate_candidate. The code lets callers group "
            "repeat observations across candidates and runs without parsing prose. "
            "It must start lowercase and use only lowercase letters, digits, and "
            "underscores."
        ),
    )
    severity: CritiqueIssueSeverity = Field(
        description=(
            "How urgently this single issue should affect the caller's decision. "
            "Use blocker when the candidate cannot proceed as written, major when it "
            "needs repair before trust, and minor or note when it is worth knowing "
            "but not decisive. Use info for observations that aid judgment without "
            "asking for any change."
        ),
    )
    fields: tuple[str, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Candidate field names this issue touches, such as expected_benefit or "
            "first_action. Naming fields lets the revision turn target its fix "
            "instead of rewriting the whole candidate. Leave empty when the issue "
            "concerns the candidate as a whole rather than specific fields."
        ),
    )
    evidence_refs: tuple[str, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Stable context references backing this observation, such as ctx-001. "
            "Every defect or tradeoff claim must point at the evidence that shows "
            "it, so callers can verify without rereading provider logs. Leave empty "
            "only when the issue needs no evidence, such as an internal incoherence."
        ),
    )
    explanation: str = Field(
        min_length=1,
        max_length=2048,
        description=(
            "What the issue is and why it matters for this candidate. "
            "State the defect or tradeoff plainly and connect it to the cited "
            "fields and evidence. Keep it to the facts a caller needs to decide, "
            "not a restatement of the whole review."
        ),
    )
    repair: str = Field(
        default="",
        max_length=2048,
        description=(
            "Concrete correction the revision turn can apply, left empty when none "
            "exists. A repair must be specific enough to execute, such as restating "
            "a benefit as an assumption or citing the missing reference. Do not "
            "offer a repair that the supplied evidence cannot support."
        ),
    )


class SuggestionCritique(BaseModel):
    """The critic artifact for exactly one candidate ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    idea_id: str = Field(pattern=r"^idea-\d{3}$")
    verdict: CritiqueVerdict
    confidence: CritiqueConfidence
    error_spans: tuple[str, ...] = Field(default=(), max_length=12)
    evidence_check: CritiqueEvidenceCheck
    evidence_ref: str | None = None
    constraint_hit: CritiqueConstraint = CritiqueConstraint.NONE
    constraint_quote: str = Field(default="", max_length=2048)
    duplicate_of: str | None = None
    fix_instruction: str = Field(default="", max_length=2048)
    preserve: tuple[str, ...] = Field(default=(), max_length=24)
    review_summary: str = Field(min_length=1, max_length=2048)
    signals: SuggestionCritiqueSignals = Field(
        default_factory=SuggestionCritiqueSignals,
        description=(
            "Multidimensional quality and decision observations for this candidate. "
            "These signals describe tradeoffs for the caller and never override the "
            "explicit verdict, which remains the sole loop control signal alongside "
            "the hard-reject rules. Defaults are unknown so older providers stay valid."
        ),
    )
    issues: tuple[SuggestionCritiqueIssue, ...] = Field(
        default=(),
        max_length=12,
        description=(
            "Traceable defects or tradeoffs the caller should see, at most twelve. "
            "Each issue carries a stable code, a severity, and the evidence behind "
            "it so result consumers can inspect findings without reading provider "
            "logs. Empty when the critique needs no visible issue beyond the verdict."
        ),
    )

    @model_validator(mode="after")
    def _validate_review_contract(self) -> SuggestionCritique:
        if self.verdict is CritiqueVerdict.REVISE and not self.fix_instruction.strip():
            raise ValueError("a revise verdict must include a fix instruction")
        if self.constraint_hit is not CritiqueConstraint.NONE and not self.constraint_quote.strip():
            raise ValueError("a constraint hit must include a supporting quote")
        if self.duplicate_of == self.idea_id:
            raise ValueError("a candidate cannot be a duplicate of itself")
        return self


class SuggestionCritiqueArtifact(BaseModel):
    """Complete per-candidate review returned by the independent critic."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    critiques: tuple[SuggestionCritique, ...] = Field(max_length=30)


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
    suggested_actions: tuple[str, ...] = Field(min_length=1, max_length=12)
    decision_points: tuple[str, ...] = Field(default=(), max_length=12)
    considerations: tuple[str, ...] = Field(default=(), min_length=8, max_length=10)
    completion_criteria: str = Field(min_length=1, max_length=1024)
    effort_estimate: str = Field(min_length=1, max_length=256)
    review_summary: str = Field(min_length=1, max_length=2048)
    critique: SuggestionCritique | None = Field(
        default=None,
        description=(
            "Accepted critique for this idea, carrying the verdict, signals, and "
            "issues behind the review summary. Present only on ideas that survived "
            "independent critique, so result consumers can inspect the reasoning "
            "without reading provider logs. None on unreviewed drafts."
        ),
    )
    handoff: SuggestionHandoff


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
    category_coverage: dict[str, int] = Field(default_factory=dict)
    missing_context: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: dict[str, int] = Field(default_factory=dict)
    stop_reason: StopReason = StopReason.COMPLETED
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v2")


__all__ = [
    "ContextManifestEntry",
    "CritiqueConfidence",
    "CritiqueConstraint",
    "CritiqueEvidenceCheck",
    "CritiqueIssueSeverity",
    "CritiqueRiskLevel",
    "CritiqueSignalLevel",
    "CritiqueVerdict",
    "IdeaHorizon",
    "IdeaReadiness",
    "IdeaRelationship",
    "MAX_CONTEXT_CHARS",
    "RunStatus",
    "SCHEMA_VERSION",
    "SUGGESTIONS_HANDOFF_KIND",
    "SUGGESTIONS_RESULT_KIND",
    "StopReason",
    "SuggestionCandidateBatch",
    "SuggestionContextItem",
    "SuggestionContextPrimitive",
    "SuggestionCritique",
    "SuggestionCritiqueArtifact",
    "SuggestionCritiqueIssue",
    "SuggestionCritiqueSignals",
    "SuggestionDraft",
    "SuggestionHandoff",
    "SuggestionHandoffEvidence",
    "SuggestionHorizon",
    "SuggestionIdea",
    "SuggestionRequest",
    "SuggestionResult",
    "SuggestionSettings",
]
