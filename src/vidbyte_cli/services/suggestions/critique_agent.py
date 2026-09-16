"""Owns critic calls and deterministic keep, revise, and reject policy."""

from __future__ import annotations

from typing import cast

from ...types.suggestions import (
    CritiqueConfidence,
    CritiqueConstraint,
    CritiqueEvidenceCheck,
    CritiqueVerdict,
    SuggestionCritique,
    SuggestionCritiqueArtifact,
    SuggestionIdea,
    SuggestionRequest,
)
from .categories import SuggestionCategories
from .context_bridge import SuggestionContextBridge
from .generator_agent import AgentCall
from .prompts.library import SuggestionPrompts


class SuggestionCritiqueAgent:
    """Reviews every candidate and returns explicit loop decisions."""

    def __init__(
        self,
        categories: SuggestionCategories,
        prompts: SuggestionPrompts,
        bridge: SuggestionContextBridge,
    ) -> None:
        # Dependencies are injected so review policy is independently replaceable.
        self._categories = categories
        self._prompts = prompts
        self._bridge = bridge

    async def critique(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        ideas: tuple[SuggestionIdea, ...],
        call: AgentCall,
    ) -> SuggestionCritiqueArtifact:
        # The critic sees one compact candidate packet and no generator deliberation.
        context = self._bridge.critic(request, category_ids, ideas)
        ids = ", ".join(idea.id for idea in ideas)
        prompt = self._prompts.critic_turn(request.goal, ids)
        return cast(
            SuggestionCritiqueArtifact,
            await call("critic", prompt, context, request.settings.critic_model),
        )

    def review(
        self, ideas: tuple[SuggestionIdea, ...], artifact: SuggestionCritiqueArtifact
    ) -> tuple[tuple[SuggestionIdea, ...], tuple[tuple[SuggestionIdea, SuggestionCritique], ...]]:
        # Enforces one exact critique per candidate before applying any verdict.
        critiques = {item.idea_id: item for item in artifact.critiques}
        if set(critiques) != {idea.id for idea in ideas} or len(critiques) != len(
            artifact.critiques
        ):
            raise ValueError("critic artifact must contain exactly one review for every candidate")
        kept: list[SuggestionIdea] = []
        revisions: list[tuple[SuggestionIdea, SuggestionCritique]] = []
        for idea in ideas:
            critique = critiques[idea.id]
            hard_reject = (
                critique.constraint_hit is not CritiqueConstraint.NONE
                or critique.evidence_check is CritiqueEvidenceCheck.CONTRADICTS
                or (
                    critique.verdict is CritiqueVerdict.REJECT
                    and critique.confidence is not CritiqueConfidence.LOW
                )
            )
            if critique.duplicate_of and critique.duplicate_of != idea.id:
                continue
            if hard_reject:
                continue
            needs_revision = (
                critique.verdict is CritiqueVerdict.REVISE
                or critique.evidence_check is CritiqueEvidenceCheck.MISSING
                or (
                    critique.verdict is CritiqueVerdict.REJECT
                    and critique.confidence is CritiqueConfidence.LOW
                )
            )
            if needs_revision:
                revisions.append((idea, critique))
                continue
            if critique.verdict is CritiqueVerdict.KEEP:
                kept.append(idea.model_copy(update={"review_summary": critique.review_summary}))
        return tuple(kept), tuple(revisions)


__all__ = ["SuggestionCritiqueAgent"]
