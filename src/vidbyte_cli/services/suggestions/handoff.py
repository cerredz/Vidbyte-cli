"""Builds deterministic execution handoffs from validated suggestion fields."""

from __future__ import annotations

from ...types.suggestions import (
    SuggestionDraft,
    SuggestionHandoff,
    SuggestionHandoffEvidence,
    SuggestionIdea,
    SuggestionRequest,
)


class SuggestionHandoffBuilder:
    """Builds one self-contained action packet without another model call."""

    def build(self, idea: SuggestionIdea, request: SuggestionRequest) -> SuggestionHandoff:
        """Rebuild a handoff from the idea fields so the prompt cannot drift."""
        return self._build(
            idea_id=idea.id,
            revision=idea.revision,
            title=idea.title,
            summary=idea.summary,
            actions=idea.suggested_actions,
            decisions=idea.decision_points,
            considerations=idea.considerations,
            evidence_refs=idea.evidence_refs,
            completion=idea.completion_criteria,
            dependencies=idea.dependencies,
            why_now=idea.why_now,
            request=request,
        )

    def build_draft(
        self, draft: SuggestionDraft, request: SuggestionRequest, idea_id: str, revision: int
    ) -> SuggestionHandoff:
        """Build the provisional handoff used when the critic sees generated candidates."""
        return self._build(
            idea_id=idea_id,
            revision=revision,
            title=draft.title,
            summary=draft.summary,
            actions=draft.suggested_actions,
            decisions=draft.decision_points,
            considerations=draft.considerations,
            evidence_refs=draft.evidence_refs,
            completion=draft.completion_criteria,
            dependencies=draft.dependencies,
            why_now=draft.why_now,
            request=request,
        )

    def _build(
        self,
        *,
        idea_id: str,
        revision: int,
        title: str,
        summary: str,
        actions: tuple[str, ...],
        decisions: tuple[str, ...],
        considerations: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        completion: str,
        dependencies: tuple[str, ...],
        why_now: str,
        request: SuggestionRequest,
    ) -> SuggestionHandoff:
        handoff = SuggestionHandoff(
            idea_id=idea_id,
            idea_revision=revision,
            original_goal=request.goal,
            title=title,
            summary=summary,
            suggested_actions=actions,
            decisions_along_way=decisions,
            considerations=considerations,
            evidence=self._evidence(evidence_refs, request, why_now),
            completion_checks=(completion,),
            dependencies=dependencies,
            warnings=self._warnings(request),
            forbidden_actions=self._context_values(request, "forbidden"),
            stop_conditions=(
                "The completion checks pass.",
                "Evidence contradicts the proposed action.",
                "Required authority is missing.",
                "Required prerequisites are missing.",
            ),
            return_report=(
                "Report actions taken, decisions made, evidence observed, completion checks, "
                "and unresolved follow-ups to the calling agent."
            ),
            execution_prompt="pending",
        )
        return handoff.model_copy(update={"execution_prompt": self.render_prompt(handoff)})

    def render_prompt(self, handoff: SuggestionHandoff) -> str:
        """Render only validated fields in a stable order."""
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
        self, refs: tuple[str, ...], request: SuggestionRequest, why_now: str
    ) -> tuple[SuggestionHandoffEvidence, ...]:
        items_by_ref = {item.ref: item for item in request.context_items}
        return tuple(
            SuggestionHandoffEvidence(
                ref=ref,
                source=items_by_ref[ref].source,
                content=items_by_ref[ref].content[:4096],
                relevance=f"Supports why this action matters now: {why_now}",
            )
            for ref in refs
            if ref in items_by_ref
        )

    def _warnings(self, request: SuggestionRequest) -> tuple[str, ...]:
        warnings = list(request.context_warnings)
        for item in request.context_items:
            if item.kind == "mistake":
                parts = tuple(part.strip() for part in item.content.split("|"))
                if len(parts) == 3 and all(parts):
                    warnings.append(
                        f"Past mistake lesson: {parts[2]} (failure: {parts[0]}; cause: {parts[1]})"
                    )
                else:
                    warnings.append(item.content)
            elif item.kind == "risk" or (
                item.kind == "hypothesis" and item.content.lower().startswith("low:")
            ):
                warnings.append(item.content)
        return tuple(dict.fromkeys(warnings))

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


__all__ = ["SuggestionHandoffBuilder"]
