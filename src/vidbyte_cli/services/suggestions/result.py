"""Builds deterministic reviewed-idea and result envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ...types.suggestions import (
    RunStatus,
    StopReason,
    SuggestionHorizon,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
)
from .categories import SuggestionCategories
from .handoff import SuggestionHandoffBuilder
from .selection import SuggestionSelection


@dataclass(frozen=True, slots=True)
class SuggestionWorkflowOutcome:
    """Fully reviewed ideas plus accounting and the reason the loop stopped."""

    ideas: tuple[SuggestionIdea, ...]
    usage: dict[str, int]
    stop_reason: StopReason
    warnings: tuple[str, ...] = ()


class SuggestionResultBuilder:
    """Owns final selection, handoff refresh, and the public result envelope."""

    def __init__(
        self,
        categories: SuggestionCategories,
        selection: SuggestionSelection,
        handoffs: SuggestionHandoffBuilder,
    ) -> None:
        # Selection and handoff collaborators keep output policy out of the workflow loop.
        self._categories = categories
        self._selection = selection
        self._handoffs = handoffs

    def merge_reviewed(
        self, previous: tuple[SuggestionIdea, ...], current: tuple[SuggestionIdea, ...]
    ) -> tuple[SuggestionIdea, ...]:
        # Carries kept candidates across a revision round without changing stable order.
        merged = {idea.id: idea for idea in previous}
        merged.update({idea.id: idea for idea in current})
        return tuple(merged.values())

    def finalize(
        self, ideas: tuple[SuggestionIdea, ...], request: SuggestionRequest
    ) -> tuple[SuggestionIdea, ...]:
        # Applies category, evidence, duplicate, rejection, horizon, handoff, and rank policies.
        allowed = set(self._categories.ids())
        manifest_refs = {
            entry.ref for entry in request.context_manifest if entry.status != "omitted"
        }
        if not manifest_refs:
            manifest_refs = {item.ref for item in request.context_items}
        selected = self._selection.validate_categories(ideas, allowed)
        selected = self._selection.validate_evidence(selected, manifest_refs)
        selected = self._selection.deduplicate(selected)
        selected = self._selection.suppress_rejected(selected, self._rejected_terms(request))
        if request.settings.horizon is not SuggestionHorizon.ANY:
            selected = tuple(
                idea for idea in selected if idea.horizon.value == request.settings.horizon.value
            )
        selected = tuple(self._handoff_refresh(idea, request) for idea in selected)
        return self._selection.rank(selected, request.settings.requested_count)

    def build(
        self, request: SuggestionRequest, outcome: SuggestionWorkflowOutcome
    ) -> SuggestionResult:
        # Adds user-facing status, shortfall warnings, and missing-context diagnostics.
        ideas = outcome.ideas
        warnings = list(outcome.warnings)
        if outcome.stop_reason is StopReason.COUNT_SHORTFALL and ideas:
            warnings.append(
                f"Only {len(ideas)} worthwhile suggestions survived review; no filler was added."
            )
        status = (
            RunStatus.NO_SUGGESTIONS
            if not ideas
            else RunStatus.COMPLETE
            if outcome.stop_reason is StopReason.COMPLETED
            else RunStatus.PARTIAL
        )
        present_kinds = {item.kind for item in request.context_items}
        missing = tuple(
            kind
            for kind in (
                "completed",
                "in_progress",
                "decision",
                "constraint",
                "risks",
                "trajectory",
            )
            if kind not in present_kinds
        )
        return SuggestionResult(
            run_id=f"sug-{uuid4().hex[:12]}",
            status=status,
            goal=request.goal,
            requested_count=request.settings.requested_count,
            returned_count=len(ideas),
            settings=request.settings,
            context_manifest=request.context_manifest,
            ideas=ideas,
            category_coverage=self._selection.coverage(ideas),
            missing_context=missing,
            warnings=tuple(dict.fromkeys(warnings)),
            usage=outcome.usage,
            stop_reason=outcome.stop_reason,
            prompt_version=request.prompt_version,
        )

    def _handoff_refresh(self, idea: SuggestionIdea, request: SuggestionRequest) -> SuggestionIdea:
        # Rebuilds deterministic evidence and execution text after final selection.
        return idea.model_copy(update={"handoff": self._handoffs.build(idea, request)})

    def _rejected_terms(self, request: SuggestionRequest) -> tuple[str, ...]:
        # Keeps completed, in-progress, and forbidden caller statements out of final output.
        return tuple(
            item.content
            for item in request.context_items
            if item.kind in {"completed", "in_progress", "avoid", "mistakes", "forbidden"}
        )


__all__ = ["SuggestionResultBuilder", "SuggestionWorkflowOutcome"]
