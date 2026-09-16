"""Versioned contracts for the suggestion (next-action) agent.

The CLI owns these shapes so commands, services, and output rendering share one
source of truth. All models are frozen and forbid extras, so contract drift fails
before a model call rather than after. No transport or provider code lives here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    content: str = Field(min_length=1, max_length=65536)
    source: str = Field(min_length=1, max_length=512)
    caller_supplied: bool = True


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

    model_config = ConfigDict(extra="forbid", frozen=True)
    goal: str = Field(min_length=1, max_length=4096)
    context_items: tuple[SuggestionContextItem, ...] = ()
    settings: SuggestionSettings
    prompt_version: str = Field(min_length=1, max_length=64, default="suggestions.v1")


class SuggestionProblem(BaseModel):
    """Explains the condition or opportunity a suggestion addresses."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["problem", "opportunity"]
    condition: str = Field(min_length=1, max_length=2048)
    consequence: str = Field(min_length=1, max_length=2048)
    affected_area: str = Field(min_length=1, max_length=512)


class SuggestionGoalContribution(BaseModel):
    """Connects a suggestion to a concrete part of the caller's goal."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    target: str = Field(min_length=1, max_length=2048)
    contribution: str = Field(min_length=1, max_length=2048)


class SuggestionExpectedChange(BaseModel):
    """States the observable before-and-after change a suggestion targets."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    before: str = Field(min_length=1, max_length=2048)
    after: str = Field(min_length=1, max_length=2048)


class SuggestionScope(BaseModel):
    """Defines the work included and excluded by a suggestion."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    in_scope: tuple[str, ...] = Field(min_length=1, max_length=8)
    out_of_scope: tuple[str, ...] = Field(min_length=1, max_length=8)


class SuggestionDecisionPoint(BaseModel):
    """Maps an execution condition to the response it requires."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    condition: str = Field(min_length=1, max_length=2048)
    response: str = Field(min_length=1, max_length=2048)
    requires_authority: bool = False


class SuggestionVerification(BaseModel):
    """Describes one procedure for proving a suggestion worked."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    claim: str = Field(min_length=1, max_length=2048)
    procedure: str = Field(min_length=1, max_length=2048)
    pass_condition: str = Field(min_length=1, max_length=2048)
    evidence_to_capture: str = Field(min_length=1, max_length=2048)
    on_failure: str = Field(min_length=1, max_length=2048)


class SuggestionTradeoff(BaseModel):
    """Names a cost of the suggestion and why it remains acceptable."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    cost: str = Field(min_length=1, max_length=2048)
    reason_acceptable: str = Field(min_length=1, max_length=2048)
    mitigation: str = Field(min_length=1, max_length=2048)


class SuggestionRisk(BaseModel):
    """Describes a plausible failure mode and its guard."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    failure_mode: str = Field(min_length=1, max_length=2048)
    likelihood: Literal["low", "medium", "high"]
    impact: Literal["low", "medium", "high"]
    guard: str = Field(min_length=1, max_length=2048)


class SuggestionUnknown(BaseModel):
    """Records an unanswered question and how to resolve it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    question: str = Field(min_length=1, max_length=2048)
    importance: str = Field(min_length=1, max_length=2048)
    resolution_method: str = Field(min_length=1, max_length=2048)


class SuggestionConfidence(BaseModel):
    """Carries a qualitative confidence level with its evidence basis."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    level: Literal["low", "medium", "high"]
    basis: tuple[str, ...] = Field(min_length=1, max_length=8)
    would_change_with: tuple[str, ...] = Field(max_length=8)


class SuggestionAlternative(BaseModel):
    """Explains a materially different option that was not selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    alternative: str = Field(min_length=1, max_length=2048)
    reason_not_selected: str = Field(min_length=1, max_length=2048)


class SuggestionReversibility(BaseModel):
    """States how difficult it is to undo a suggestion and recover."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    level: Literal["reversible", "partly_reversible", "hard_to_reverse"]
    reason: str = Field(min_length=1, max_length=2048)
    recovery: str = Field(min_length=1, max_length=2048)


class SuggestionTimeSensitivity(BaseModel):
    """Explains whether delay changes the suggestion's value."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    level: Literal["low", "medium", "high"]
    trigger: str = Field(min_length=1, max_length=2048)
    expires_when: str | None = Field(default=None, max_length=512)


class SuggestionContext(BaseModel):
    """Structured reasoning and decision context behind one suggestion."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    problem_or_opportunity: SuggestionProblem
    core_insight: str = Field(min_length=1, max_length=2048)
    causal_rationale: str = Field(min_length=1, max_length=2048)
    goal_contribution: SuggestionGoalContribution
    expected_change: SuggestionExpectedChange
    scope: SuggestionScope
    decision_points: tuple[SuggestionDecisionPoint, ...] = Field(min_length=1, max_length=8)
    verification_plan: tuple[SuggestionVerification, ...] = Field(min_length=1, max_length=8)
    final_success_condition: str = Field(min_length=1, max_length=2048)
    beneficiaries: tuple[str, ...] = Field(min_length=1, max_length=8)
    affected_surfaces: tuple[str, ...] = Field(min_length=1, max_length=8)
    tradeoffs: tuple[SuggestionTradeoff, ...] = Field(min_length=1, max_length=8)
    risks: tuple[SuggestionRisk, ...] = Field(min_length=1, max_length=8)
    unknowns: tuple[SuggestionUnknown, ...] = Field(min_length=1, max_length=8)
    confidence: SuggestionConfidence
    alternatives_considered: tuple[SuggestionAlternative, ...] = Field(min_length=1, max_length=8)
    cost_of_inaction: str = Field(min_length=1, max_length=2048)
    reversibility: SuggestionReversibility
    time_sensitivity: SuggestionTimeSensitivity


class SuggestionHandoff(BaseModel):
    """Portable execution packet for one idea; authority is never granted here."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    handoff_version: Literal[2] = 2
    idea_id: str = Field(min_length=1, max_length=64)
    idea_revision: int = Field(ge=1)
    suggestion_title: str = Field(min_length=1, max_length=256)
    suggestion_summary: str = Field(min_length=1, max_length=2048)
    primary_category: str = Field(min_length=1, max_length=64)
    secondary_categories: tuple[str, ...] = Field(max_length=8)
    horizon: IdeaHorizon
    relationship: IdeaRelationship
    readiness: IdeaReadiness
    expected_benefit: str = Field(min_length=1, max_length=1024)
    effort_estimate: str = Field(min_length=1, max_length=256)
    review_summary: str = Field(min_length=1, max_length=1024)
    evidence_refs: tuple[str, ...] = Field(max_length=16)
    suggestion_context: SuggestionContext
    original_goal: str = Field(min_length=1, max_length=4096)
    selected_action: str = Field(min_length=1, max_length=2048)
    reason_for_selection: str = Field(min_length=1, max_length=2048)
    current_state: str = Field(min_length=1, max_length=4096)
    relevant_decisions: tuple[str, ...] = ()
    completed_work: tuple[str, ...] = ()
    in_progress_work: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    assumptions_to_verify: tuple[str, ...] = ()
    suggested_steps: tuple[str, ...] = Field(min_length=1)
    deliverables: tuple[str, ...] = ()
    acceptance_checks: tuple[str, ...] = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
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
    proposed_action: str = Field(min_length=1, max_length=2048)
    completion_criteria: str = Field(min_length=1, max_length=1024)
    effort_estimate: str = Field(min_length=1, max_length=256)
    review_summary: str = Field(min_length=1, max_length=1024)
    suggestion_context: SuggestionContext
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
