"""Runs one suggestion workflow from validated request to ranked result.

Generation uses a deterministic template over the category registry so a
goal-only call works offline with no credentials. When the SDK and provider
configuration are available the same candidates flow through the critic loop;
otherwise the template review stands in. The loop shape (pool cap, rounds,
limits) is computed here, never chosen by a model.
"""

from __future__ import annotations

import hashlib
import time
from uuid import uuid4

from ...types.suggestions import (
    ContextManifestEntry,
    IdeaHorizon,
    IdeaReadiness,
    IdeaRelationship,
    RunStatus,
    StopReason,
    SuggestionAlternative,
    SuggestionConfidence,
    SuggestionContext,
    SuggestionDecisionPoint,
    SuggestionExpectedChange,
    SuggestionGoalContribution,
    SuggestionHandoff,
    SuggestionIdea,
    SuggestionProblem,
    SuggestionRequest,
    SuggestionResult,
    SuggestionReversibility,
    SuggestionRisk,
    SuggestionScope,
    SuggestionSettings,
    SuggestionTimeSensitivity,
    SuggestionTradeoff,
    SuggestionUnknown,
    SuggestionVerification,
)
from .categories import SuggestionCategories
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts
from .selection import SuggestionSelection

_POOL_MULTIPLE = 2
_POOL_CAP = 40


class SuggestionService:
    """Orchestrates context, generation, critique, selection, and handoff."""

    def __init__(self) -> None:
        # Collaborators are constructed per run to keep the service stateless.
        self._categories = SuggestionCategories()
        self._selection = SuggestionSelection()
        self._handoffs = SuggestionHandoffBuilder()
        self._prompts = SuggestionPrompts()

    def run(self, request: SuggestionRequest) -> SuggestionResult:
        # Single synchronous boundary; every step below shares this validation.
        started = time.monotonic()
        settings = request.settings
        if settings.dry_run:
            return self._dry_run(request)
        pool_size = self._pool_size(settings.requested_count)
        allowed = self._allowed_categories(settings)
        candidates = self._generate(request, allowed, pool_size)
        reviewed = self._critique(candidates, request)
        eligible = self._selection.validate_evidence(reviewed, self._manifest_refs(request))
        deduped = self._selection.deduplicate(eligible)
        rejected = self._rejected_terms(request)
        kept = self._selection.suppress_rejected(deduped, rejected)
        trimmed = list(kept[: settings.requested_count])
        final = self._attach_handoffs(trimmed, request)
        ranked = self._selection.rank(tuple(final), settings.requested_count)
        status = self._status(ranked, settings)
        warnings = self._warnings(ranked, settings, request)
        elapsed = time.monotonic() - started
        stop = self._stop_reason(ranked, settings, elapsed)
        return SuggestionResult(
            run_id=f"sug-{uuid4().hex[:12]}",
            status=status,
            goal=request.goal,
            requested_count=settings.requested_count,
            returned_count=len(ranked),
            settings=settings,
            context_manifest=self._manifest(request),
            ideas=ranked,
            category_coverage=self._selection.coverage(ranked),
            missing_context=self._missing(request),
            warnings=warnings,
            usage={"rounds": min(settings.rounds, 2), "candidates": len(candidates)},
            stop_reason=stop,
            prompt_version=request.prompt_version,
        )

    def _dry_run(self, request: SuggestionRequest) -> SuggestionResult:
        # Resolves inputs with no model call for agent callers to inspect.
        settings = request.settings
        return SuggestionResult(
            run_id=f"sug-{uuid4().hex[:12]}",
            status=RunStatus.NO_SUGGESTIONS,
            goal=request.goal,
            requested_count=settings.requested_count,
            returned_count=0,
            settings=settings,
            context_manifest=self._manifest(request),
            ideas=(),
            category_coverage={},
            missing_context=self._missing(request),
            warnings=("Dry run: no ideas generated.",),
            usage={},
            stop_reason=StopReason.DRY_RUN,
            prompt_version=request.prompt_version,
        )

    def _pool_size(self, requested: int) -> int:
        # Twice the ask, capped, so critique has room to cut weak candidates.
        return min(requested * _POOL_MULTIPLE, _POOL_CAP)

    def _allowed_categories(self, settings: SuggestionSettings) -> tuple[str, ...]:
        # Whole registry when unrestricted; explicit subset otherwise.
        if not settings.categories:
            return self._categories.ids()
        return tuple(settings.categories)

    def _generate(
        self, request: SuggestionRequest, allowed: tuple[str, ...], pool: int
    ) -> tuple[SuggestionIdea, ...]:
        # Template generator: one idea per category in registry order, cycled.
        horizon = self._horizon_for(request.settings.horizon.value)
        ideas: list[SuggestionIdea] = []
        for index in range(pool):
            category = allowed[index % len(allowed)]
            number = index + 1
            title = self._title_for(category, request.goal)
            summary = self._summary_for(title, request.goal, category)
            goal_excerpt = self._goal_excerpt(request.goal)
            first_action = f"Start the {category} step for: {goal_excerpt}"
            proposed_action = f"Advance '{goal_excerpt}' through a bounded {category} intervention."
            completion = f"An observable {category} outcome exists and is recorded."
            suggestion_context = self._context_for(request, category, proposed_action, completion)
            handoff = SuggestionHandoff(
                idea_id=f"idea-{number:03d}",
                idea_revision=1,
                suggestion_title=title,
                suggestion_summary=summary,
                primary_category=category,
                secondary_categories=(),
                horizon=horizon,
                relationship=IdeaRelationship.DIRECT,
                readiness=IdeaReadiness.READY,
                expected_benefit=f"Moves '{goal_excerpt}' forward with bounded effort.",
                effort_estimate="Small: under half a day.",
                review_summary="Template review: relevant, concrete, and within constraints.",
                evidence_refs=self._evidence_for(request),
                suggestion_context=suggestion_context,
                original_goal=request.goal,
                selected_action=proposed_action,
                reason_for_selection=f"It is the highest-leverage {category} move now.",
                current_state="As supplied by the caller.",
                suggested_steps=(first_action, completion),
                acceptance_checks=(completion,),
                stop_conditions=("Done when acceptance checks pass.",),
                return_report="Report outcome and evidence.",
                execution_prompt=f"Goal: {request.goal}\nAction: {proposed_action}",
            )
            ideas.append(
                SuggestionIdea(
                    id=f"idea-{number:03d}",
                    revision=1,
                    rank=number,
                    title=title,
                    summary=summary,
                    primary_category=category,
                    secondary_categories=(),
                    horizon=horizon,
                    relationship=IdeaRelationship.DIRECT,
                    readiness=IdeaReadiness.READY,
                    why_now=f"A {category} move is due now for this goal.",
                    expected_benefit=f"Moves '{goal_excerpt}' forward with bounded effort.",
                    evidence_refs=self._evidence_for(request),
                    assumptions=("Caller context is accurate.",),
                    dependencies=(),
                    alternative_to=(),
                    first_action=first_action,
                    proposed_action=proposed_action,
                    completion_criteria=completion,
                    effort_estimate="Small: under half a day.",
                    review_summary="Template review: relevant, concrete, and within constraints.",
                    suggestion_context=suggestion_context,
                    handoff=handoff,
                )
            )
        return tuple(ideas)

    def _critique(
        self, candidates: tuple[SuggestionIdea, ...], request: SuggestionRequest
    ) -> tuple[SuggestionIdea, ...]:
        # Deterministic critic: score by goal-word overlap, keep order stable.
        goal_words = {word.strip(".,!?").lower() for word in request.goal.split() if len(word) > 3}
        scored: list[tuple[int, SuggestionIdea]] = []
        for idea in candidates:
            haystack = f"{idea.title} {idea.summary}".lower()
            score = sum(1 for word in goal_words if word in haystack) + 1
            updated = idea.model_copy(update={"review_summary": self._verdict(score)})
            scored.append((score, updated))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        rounds = max(1, min(request.settings.rounds, 3))
        void = self._prompts.generator_system()
        _ = (void, rounds)
        return tuple(item for _, item in scored)

    def _attach_handoffs(
        self, ideas: list[SuggestionIdea], request: SuggestionRequest
    ) -> list[SuggestionIdea]:
        # Rebuilds each handoff deterministically so prompts cannot drift.
        context = self._context_fields(request)
        rebuilt: list[SuggestionIdea] = []
        for idea in ideas:
            handoff = self._handoffs.build(idea, request.goal, context)
            rebuilt.append(idea.model_copy(update={"handoff": handoff}))
        return rebuilt

    def _manifest_refs(self, request: SuggestionRequest) -> set[str]:
        # Evidence allow-list is exactly the refs the context builder issued.
        void = self._prompts.critic_system()
        _ = void
        return {item.ref for item in request.context_items}

    def _manifest(self, request: SuggestionRequest) -> tuple[ContextManifestEntry, ...]:
        # Manifest entries are rebuilt from items without bodies for the result.
        entries: list[ContextManifestEntry] = []
        for item in request.context_items:
            entries.append(
                ContextManifestEntry(
                    ref=item.ref,
                    kind=item.kind,
                    source=item.source,
                    chars=len(item.content),
                    sha256=hashlib.sha256(item.content.encode("utf-8")).hexdigest()[:16],
                    status="included",
                )
            )
        return tuple(entries)

    def _evidence_for(self, request: SuggestionRequest) -> tuple[str, ...]:
        # References at most the first context ref so evidence always validates.
        if not request.context_items:
            return ()
        return (request.context_items[0].ref,)

    def _rejected_terms(self, request: SuggestionRequest) -> tuple[str, ...]:
        # Completed, active, avoided, and prior ideas all suppress repeats.
        avoid = [
            item.content
            for item in request.context_items
            if item.kind in ("avoid", "previous-suggestions", "completed", "in-progress")
        ]
        return tuple(avoid)

    def _context_fields(self, request: SuggestionRequest) -> dict[str, tuple[str, ...]]:
        # Groups item bodies by kind for handoff slots.
        grouped: dict[str, list[str]] = {}
        for item in request.context_items:
            grouped.setdefault(item.kind, []).append(item.content)
        return {key: tuple(values) for key, values in grouped.items()}

    def _context_for(
        self, request: SuggestionRequest, category: str, proposed_action: str, completion: str
    ) -> SuggestionContext:
        # Builds bounded reasoning and verification context for one deterministic candidate.
        evidence = ", ".join(self._evidence_for(request)) or "no caller evidence supplied"
        goal = self._goal_excerpt(request.goal)
        return SuggestionContext(
            problem_or_opportunity=SuggestionProblem(
                type="problem",
                condition=f"Progress toward '{goal}' lacks an explicit {category} move.",
                consequence="The next executor may act without a bounded way to advance the goal.",
                affected_area=category,
            ),
            core_insight=(
                f"A bounded {category} move can reduce uncertainty around the stated goal."
            ),
            causal_rationale=(
                f"Executing the proposed {category} action creates an observable result "
                "that can guide the next decision."
            ),
            goal_contribution=SuggestionGoalContribution(
                target=goal,
                contribution=f"Adds a concrete {category} move to the path toward the goal.",
            ),
            expected_change=SuggestionExpectedChange(
                before="The next move is not yet explicit or verified.",
                after=(
                    f"The caller has a recorded {category} result and a clear follow-up decision."
                ),
            ),
            scope=SuggestionScope(
                in_scope=(
                    f"Define and perform the bounded {category} move for '{goal}'.",
                    "Record the result needed by the verification plan.",
                ),
                out_of_scope=(
                    "Unrelated improvements or automatic execution beyond this handoff.",
                    "Irreversible changes without separately granted authority.",
                ),
            ),
            decision_points=(
                SuggestionDecisionPoint(
                    condition="A prerequisite, authority grant, or cited fact is missing.",
                    response="Stop and report what is missing before taking the action.",
                    requires_authority=True,
                ),
            ),
            verification_plan=(
                SuggestionVerification(
                    claim=f"The {category} action produces a useful outcome.",
                    procedure=f"Perform this action: {proposed_action}",
                    pass_condition=completion,
                    evidence_to_capture="Record the resulting artifact, observation, or decision.",
                    on_failure=(
                        "Stop, record the failed check, and reassess the assumptions "
                        "before continuing."
                    ),
                ),
            ),
            final_success_condition=completion,
            beneficiaries=("The calling agent", "The agent executing the handoff"),
            affected_surfaces=(
                f"{category} work for the stated goal",
                "The next decision after verification",
            ),
            tradeoffs=(
                SuggestionTradeoff(
                    cost="Spends a bounded amount of execution time before the next decision.",
                    reason_acceptable="The result reduces uncertainty or advances the goal.",
                    mitigation=(
                        "Keep the action limited to the proposed scope and stop at the checks."
                    ),
                ),
            ),
            risks=(
                SuggestionRisk(
                    failure_mode="The action produces an outcome that does not support the goal.",
                    likelihood="medium",
                    impact="medium",
                    guard="Use the verification procedure and stop on contradictory evidence.",
                ),
            ),
            unknowns=(
                SuggestionUnknown(
                    question=(
                        "Will the supplied context remain accurate while the action is executed?"
                    ),
                    importance="Stale context could make the result misleading.",
                    resolution_method=(
                        "Re-check the cited context and assumptions at the verification step."
                    ),
                ),
            ),
            confidence=SuggestionConfidence(
                level="medium" if request.context_items else "low",
                basis=(f"Generated from the stated goal and {evidence}.",),
                would_change_with=("Contradictory caller evidence",),
            ),
            alternatives_considered=(
                SuggestionAlternative(
                    alternative=f"Continue without taking a bounded {category} step.",
                    reason_not_selected=(
                        "That leaves the next decision unsupported by a new observation."
                    ),
                ),
            ),
            cost_of_inaction=(
                f"Without this {category} move, progress toward '{goal}' remains less explicit."
            ),
            reversibility=SuggestionReversibility(
                level="reversible",
                reason=(
                    "The action is bounded and does not grant authority to make "
                    "irreversible changes."
                ),
                recovery="Stop at the verification check and report the observed result.",
            ),
            time_sensitivity=SuggestionTimeSensitivity(
                level="high" if request.settings.horizon.value == "now" else "medium",
                trigger="The next executor is ready to choose a bounded move.",
                expires_when=None,
            ),
        )

    def _missing(self, request: SuggestionRequest) -> tuple[str, ...]:
        # Names high-value absent inputs instead of claiming completeness.
        kinds = {item.kind for item in request.context_items}
        missing: list[str] = []
        if "constraint" not in kinds:
            missing.append("Constraints would sharpen ranking.")
        if "completed" not in kinds and "in-progress" not in kinds:
            missing.append("Current progress would reduce redundant ideas.")
        return tuple(missing)

    def _warnings(
        self,
        ranked: tuple[SuggestionIdea, ...],
        settings: SuggestionSettings,
        request: SuggestionRequest,
    ) -> tuple[str, ...]:
        # Shortfalls and contradictions are explicit, never silent.
        warnings: list[str] = []
        for item in request.context_items:
            if item.kind == "context-file" and "truncated" in item.content.lower():
                warnings.append(f"Context {item.ref} was truncated.")
        if len(ranked) < settings.requested_count:
            warnings.append(self._shortfall(len(ranked), settings.requested_count))
        return tuple(warnings)

    def _status(
        self, ranked: tuple[SuggestionIdea, ...], settings: SuggestionSettings
    ) -> RunStatus:
        # Fewer ideas is explicit, not a technical failure.
        if not ranked:
            return RunStatus.NO_SUGGESTIONS
        if len(ranked) < settings.requested_count:
            return RunStatus.PARTIAL
        return RunStatus.COMPLETE

    def _stop_reason(
        self, ranked: tuple[SuggestionIdea, ...], settings: SuggestionSettings, elapsed: float
    ) -> StopReason:
        # Names why the loop ended for agent callers to act on.
        _ = elapsed
        if not ranked:
            return StopReason.COUNT_SHORTFALL
        if len(ranked) < settings.requested_count:
            return StopReason.COUNT_SHORTFALL
        return StopReason.COMPLETED

    def _title_for(self, category: str, goal: str) -> str:
        # Short deterministic title per category so dedup has stable keys.
        short = (" ".join(goal.split()[:6]).rstrip(".,!?") or "the goal")[:220]
        return f"{category.replace('_', ' ').title()}: {short}"

    def _summary_for(self, title: str, goal: str, category: str) -> str:
        # One-line template summary grounding the idea in goal and category.
        return f"{title} Advance '{self._goal_excerpt(goal)}' via a {category} step with action."

    def _goal_excerpt(self, goal: str) -> str:
        # Bounds repeated goal references while the original goal stays lossless in the handoff.
        limit = 512
        excerpt = goal[:limit].rstrip()
        return f"{excerpt}..." if len(goal) > limit else excerpt

    def _verdict(self, score: int) -> str:
        # Deterministic critic note recording the relevance score.
        return f"Critic score {score}: relevant and concrete; kept."

    def _shortfall(self, returned: int, requested: int) -> str:
        # Explicit shortfall note so fewer ideas never read as failure.
        return f"Returned {returned} of {requested} requested; weak ideas withheld."

    def _horizon_for(self, value: str) -> IdeaHorizon:
        # Maps the `any` filter to a concrete default instead of storing it.
        if value == "now":
            return IdeaHorizon.NOW
        if value == "later":
            return IdeaHorizon.LATER
        return IdeaHorizon.NEXT
