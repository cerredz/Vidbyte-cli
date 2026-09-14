"""Assembles deterministic, action-centered handoffs from validated ideas."""

from __future__ import annotations

from ...types.suggestions import (
    SuggestionHandoff,
    SuggestionHandoffEvidence,
    SuggestionIdea,
    SuggestionRequest,
)


class SuggestionHandoffBuilder:
    """Build one execution packet whose primary content is the proposed action."""

    def build(self, idea: SuggestionIdea, request: SuggestionRequest) -> SuggestionHandoff:
        """Turn a reviewed idea and its cited context into a self-contained handoff."""
        handoff = SuggestionHandoff(
            idea_id=idea.id,
            idea_revision=idea.revision,
            original_goal=request.goal,
            title=idea.title,
            summary=idea.summary,
            suggested_actions=idea.suggested_actions,
            decisions_along_way=idea.decision_points,
            considerations=(*idea.considerations, *idea.assumptions),
            evidence=self._evidence(idea, request),
            completion_checks=(idea.completion_criteria,),
            dependencies=idea.dependencies,
            warnings=self._warnings(request),
            forbidden_actions=self._context_values(request, "forbidden"),
            stop_conditions=self._stops(),
            return_report=(
                "Report the actions taken, decisions made, evidence observed, completion "
                "checks, and any unresolved follow-ups to the calling agent."
            ),
            execution_prompt="pending",
        )
        return handoff.model_copy(update={"execution_prompt": self.render_prompt(handoff)})

    def render_prompt(self, handoff: SuggestionHandoff) -> str:
        """Render only validated handoff fields, preserving their structured order."""
        lines = [
            f"Goal: {handoff.original_goal}",
            f"Suggested action: {handoff.title}",
            f"Summary: {handoff.summary}",
            "Actions:",
            *self._lines(handoff.suggested_actions),
            "Decisions along the way:",
            *self._lines(handoff.decisions_along_way),
            "Things to consider:",
            *self._lines(handoff.considerations),
            "Evidence:",
            *self._evidence_lines(handoff.evidence),
            "Completion checks:",
            *self._lines(handoff.completion_checks),
            "Dependencies:",
            *self._lines(handoff.dependencies),
            "Warnings:",
            *self._lines(handoff.warnings),
            "Forbidden actions:",
            *self._lines(handoff.forbidden_actions),
            "Stop when:",
            *self._lines(handoff.stop_conditions),
            f"Authority: {handoff.authority}",
            f"Report: {handoff.return_report}",
        ]
        return "\n".join(lines)

    def _evidence(
        self, idea: SuggestionIdea, request: SuggestionRequest
    ) -> tuple[SuggestionHandoffEvidence, ...]:
        items_by_ref = {item.ref: item for item in request.context_items}
        evidence: list[SuggestionHandoffEvidence] = []
        for ref in idea.evidence_refs:
            item = items_by_ref.get(ref)
            if item is None:
                continue
            evidence.append(
                SuggestionHandoffEvidence(
                    ref=ref,
                    source=item.source,
                    content=item.content[:4096],
                    relevance=f"Supports the proposed action: {idea.why_now}",
                )
            )
        return tuple(evidence)

    def _warnings(self, request: SuggestionRequest) -> tuple[str, ...]:
        warning_kinds = {"mistake", "risk"}
        warnings = [item.content for item in request.context_items if item.kind in warning_kinds]
        warnings.extend(
            item.content
            for item in request.context_items
            if item.kind == "hypothesis" and item.content.lower().startswith("low:")
        )
        return tuple(warnings)

    def _context_values(self, request: SuggestionRequest, kind: str) -> tuple[str, ...]:
        return tuple(item.content for item in request.context_items if item.kind == kind)

    def _lines(self, values: tuple[str, ...]) -> list[str]:
        return [f"- {value}" for value in values] or ["- none supplied"]

    def _evidence_lines(self, evidence: tuple[SuggestionHandoffEvidence, ...]) -> list[str]:
        if not evidence:
            return ["- none cited"]
        return [
            f"- [{item.ref}] {item.content} (source: {item.source}; {item.relevance})"
            for item in evidence
        ]

    def _stops(self) -> tuple[str, ...]:
        return (
            "The completion checks pass.",
            "Evidence contradicts the proposed action.",
            "Required authority or prerequisites are missing.",
        )
