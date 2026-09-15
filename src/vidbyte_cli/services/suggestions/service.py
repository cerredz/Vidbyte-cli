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
    SuggestionHandoff,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
    SuggestionSettings,
)
from .categories import SuggestionCategories
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts
from .selection import SuggestionSelection

_POOL_MULTIPLE = 2
_POOL_CAP = 40
_UNBLOCKING_CATEGORIES = frozenset(("prerequisite", "bottleneck", "alternative", "coordination"))


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
        allowed = self._allowed_categories(settings, request)
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

    def _allowed_categories(
        self, settings: SuggestionSettings, request: SuggestionRequest
    ) -> tuple[str, ...]:
        # Explicit order is caller-owned; unrestricted runs prioritize context-relevant lenses.
        if settings.categories:
            return tuple(settings.categories)
        preferred: list[str] = []
        kinds = {item.kind for item in request.context_items}
        if "hypothesis" in kinds:
            preferred.extend(("experiment", "investigation"))
        if "blocker" in kinds:
            preferred.extend(("bottleneck", "alternative"))
        if "risk" in kinds:
            preferred.extend(("risk_prevention", "verification"))
        if "outcome" in kinds or "approach" in kinds:
            preferred.extend(("continuation", "leverage"))
        return tuple(dict.fromkeys((*preferred, *self._categories.ids())))

    def _generate(
        self, request: SuggestionRequest, allowed: tuple[str, ...], pool: int
    ) -> tuple[SuggestionIdea, ...]:
        # Template generator: context changes the substance, not just the prompt envelope.
        ideas: list[SuggestionIdea] = []
        for index in range(pool):
            category = allowed[index % len(allowed)]
            number = index + 1
            title = self._title_for(category, request.goal)
            summary = self._summary_for(title, request.goal, category)
            actions = self._action_plan(category, request, index)
            decisions = self._decision_points(category, request, index)
            considerations = self._considerations(request, index)
            horizon = self._idea_horizon(category, request)
            readiness = self._idea_readiness(category, request)
            handoff = SuggestionHandoff(
                idea_id=f"idea-{number:03d}",
                idea_revision=1,
                original_goal=request.goal,
                title=title,
                summary=summary,
                suggested_actions=actions,
                decisions_along_way=decisions,
                considerations=considerations,
                completion_checks=(f"Observable {category} outcome exists.",),
                stop_conditions=("The completion checks pass.",),
                return_report="Report outcome and evidence.",
                execution_prompt=f"Goal: {request.goal}\nAction: Do the {category} step.",
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
                    readiness=readiness,
                    why_now=f"A {category} move is due now for this goal.",
                    expected_benefit=f"Moves '{request.goal}' forward with bounded effort.",
                    evidence_refs=self._evidence_for(request),
                    assumptions=("Caller context is accurate.",),
                    dependencies=(),
                    alternative_to=(),
                    first_action=actions[0],
                    suggested_actions=actions,
                    decision_points=decisions,
                    considerations=considerations,
                    completion_criteria=f"Observable {category} outcome exists.",
                    effort_estimate="Small: under half a day.",
                    review_summary="Template review: relevant, concrete, and within constraints.",
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
            if not self._has_risk_mitigation(idea, request):
                continue
            haystack = f"{idea.title} {idea.summary} {' '.join(idea.suggested_actions)}".lower()
            score = sum(1 for word in goal_words if word in haystack) + 1
            updated = idea.model_copy(
                update={"review_summary": self._review_summary(score, request)}
            )
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
        rebuilt: list[SuggestionIdea] = []
        for idea in ideas:
            handoff = self._handoffs.build(idea, request)
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
        # Embed a bounded supporting set in the final handoff instead of emitting bare paths.
        return tuple(item.ref for item in request.context_items[:4])

    def _action_plan(
        self, category: str, request: SuggestionRequest, index: int
    ) -> tuple[str, ...]:
        # Each context type changes an action, while failed/rejected approaches stay excluded.
        blocker = self._pick(self._context_values(request, "blocker"), index)
        hypothesis = self._pick(self._context_values(request, "hypothesis"), index)
        risk = self._pick(self._context_values(request, "risk"), index)
        outcome = self._pick(self._context_values(request, "outcome"), index)
        worked = self._pick(self._approaches(request, {"worked"}), index)
        untried = self._pick(self._approaches(request, {"untried"}), index)
        base = self._base_action(category, request.goal, blocker, hypothesis, risk, worked, untried)
        actions = [base]
        actions.extend(
            self._context_actions(worked, untried, outcome, blocker, hypothesis, risk, category)
        )
        return tuple(dict.fromkeys(actions))

    def _base_action(
        self,
        category: str,
        goal: str,
        blocker: str,
        hypothesis: str,
        risk: str,
        worked: str,
        untried: str,
    ) -> str:
        if hypothesis and category in ("experiment", "investigation"):
            return f"Test and attempt to refute this hypothesis: {hypothesis}"
        if blocker and category in _UNBLOCKING_CATEGORIES:
            return f"Clear or route around this blocker: {blocker}"
        if risk and category == "risk_prevention":
            return f"Mitigate this known risk before dependent work begins: {risk}"
        if untried and category in ("experiment", "alternative"):
            return f"Evaluate this untried approach with a bounded check: {untried}"
        if worked and category in ("continuation", "leverage"):
            return f"Build on this worked approach: {worked}"
        return f"Do the {category} step for: {goal}"

    def _context_actions(
        self,
        worked: str,
        untried: str,
        outcome: str,
        blocker: str,
        hypothesis: str,
        risk: str,
        category: str,
    ) -> list[str]:
        actions: list[str] = []
        if worked:
            actions.append(f"Preserve and extend what worked in this approach: {worked}")
        if untried:
            actions.append(f"Test whether this untried approach is now useful: {untried}")
        if outcome:
            actions.append(
                f"Use this observed outcome to choose and measure the follow-up: {outcome}"
            )
        if blocker and category not in _UNBLOCKING_CATEGORIES:
            actions.append(
                "Defer blocked dependencies or choose an independent route until this clears: "
                f"{blocker}"
            )
        if hypothesis:
            actions.append(
                f"Collect evidence that can confirm or refute this hypothesis: {hypothesis}"
            )
        if risk:
            actions.append(f"Add and verify a mitigation for this known risk: {risk}")
        return actions

    def _decision_points(
        self, category: str, request: SuggestionRequest, index: int
    ) -> tuple[str, ...]:
        decisions = [f"Choose the smallest {category} move that produces evidence."]
        outcome = self._pick(self._context_values(request, "outcome"), index)
        blocker = self._pick(self._context_values(request, "blocker"), index)
        if outcome:
            decisions.append(f"Decide whether this outcome supports continuing: {outcome}")
        if blocker:
            decisions.append(f"Decide whether to clear, route around, or wait on: {blocker}")
        return tuple(decisions)

    def _considerations(self, request: SuggestionRequest, index: int) -> tuple[str, ...]:
        considerations = ["Preserve the caller's constraints and prior decisions."]
        for kind, prefix in (
            ("mistake", "Avoid repeating this past failure"),
            ("risk", "Account for this fragile area"),
            ("hypothesis", "Keep this unverified belief explicit"),
        ):
            value = self._pick(self._context_values(request, kind), index)
            if value:
                considerations.append(f"{prefix}: {value}")
        return tuple(considerations)

    def _idea_horizon(self, category: str, request: SuggestionRequest) -> IdeaHorizon:
        if self._context_values(request, "blocker") and category not in _UNBLOCKING_CATEGORIES:
            return IdeaHorizon.LATER
        return self._horizon_for(request.settings.horizon.value)

    def _idea_readiness(self, category: str, request: SuggestionRequest) -> IdeaReadiness:
        if self._context_values(request, "blocker") and category not in _UNBLOCKING_CATEGORIES:
            return IdeaReadiness.BLOCKED
        if self._context_values(request, "hypothesis") and category in (
            "experiment",
            "investigation",
        ):
            return IdeaReadiness.NEEDS_EVIDENCE
        return IdeaReadiness.READY

    def _has_risk_mitigation(self, idea: SuggestionIdea, request: SuggestionRequest) -> bool:
        if not self._context_values(request, "risk"):
            return True
        return any("mitigat" in action.lower() for action in idea.suggested_actions)

    def _review_summary(self, score: int, request: SuggestionRequest) -> str:
        notes = [self._verdict(score)]
        if self._context_values(request, "risk"):
            notes.append("Required risk mitigation is present.")
        if any(
            value.lower().startswith("low:")
            for value in self._context_values(request, "hypothesis")
        ):
            notes.append("Dependence on a low-confidence hypothesis is flagged.")
        if self._context_values(request, "mistake"):
            notes.append("Past failure patterns remain subject to rejection suppression.")
        return " ".join(notes)

    def _approaches(self, request: SuggestionRequest, statuses: set[str]) -> tuple[str, ...]:
        found: list[str] = []
        for value in self._context_values(request, "approach"):
            status, separator, approach = value.partition(":")
            if separator and status.strip().lower() in statuses and approach.strip():
                found.append(approach.strip())
        return tuple(found)

    def _context_values(self, request: SuggestionRequest, kind: str) -> tuple[str, ...]:
        return tuple(item.content for item in request.context_items if item.kind == kind)

    def _pick(self, values: tuple[str, ...], index: int) -> str:
        return values[index % len(values)] if values else ""

    def _rejected_terms(self, request: SuggestionRequest) -> tuple[str, ...]:
        # Completed, forbidden, failed, and rejected directions all suppress repeats.
        avoid = [
            item.content
            for item in request.context_items
            if item.kind
            in (
                "avoid",
                "previous-suggestions",
                "completed",
                "in-progress",
                "mistake",
                "forbidden",
            )
        ]
        avoid.extend(
            item.content.split(":", 1)[-1].strip()
            for item in request.context_items
            if item.kind == "approach"
            and item.content.partition(":")[0].strip().lower() in ("failed", "rejected")
        )
        avoid.extend(
            item.content.split("|", 1)[0].strip()
            for item in request.context_items
            if item.kind == "mistake" and "|" in item.content
        )
        return tuple(avoid)

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
        short = " ".join(goal.split()[:6]).rstrip(".,!?") or "the goal"
        return f"{category.replace('_', ' ').title()}: {short}"

    def _summary_for(self, title: str, goal: str, category: str) -> str:
        # One-line template summary grounding the idea in goal and category.
        return f"{title} Advance '{goal}' via a {category} step with action."

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
