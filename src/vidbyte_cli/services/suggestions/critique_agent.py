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
        # The set comparison catches a missing or invented id; the length comparison catches two
        # critiques for one id, which the dict above would otherwise collapse into the later one.
        # Partial coverage is a provider fault, not a policy outcome, so it fails the round rather
        # than silently dropping the unreviewed candidates.
        if set(critiques) != {idea.id for idea in ideas} or len(critiques) != len(
            artifact.critiques
        ):
            raise ValueError("critic artifact must contain exactly one review for every candidate")
        # Candidates leave this loop by exactly one of three routes: kept, queued for revision, or
        # dropped. Dropping is the implicit fourth outcome of falling through every branch.
        kept: list[SuggestionIdea] = []
        revisions: list[tuple[SuggestionIdea, SuggestionCritique]] = []
        # Iterating the candidates rather than the critiques preserves generator rank order, which
        # the result builder relies on when it merges this round into the running set.
        for idea in ideas:
            critique = critiques[idea.id]
            # A hard reject is a drop the generator cannot argue with, and it has three sources: a
            # context boundary the candidate crosses (forbidden, already completed, or in progress),
            # evidence that actively contradicts the supplied context, or a confident reject. Each
            # is unrecoverable by rewriting, which is what separates it from the revise set below.
            hard_reject = (
                critique.constraint_hit is not CritiqueConstraint.NONE
                or critique.evidence_check is CritiqueEvidenceCheck.CONTRADICTS
                or (
                    critique.verdict is CritiqueVerdict.REJECT
                    and critique.confidence is not CritiqueConfidence.LOW
                )
            )
            # Duplicates are dropped ahead of every other branch, whatever their verdict: the peer
            # they point at is already carrying this idea, so reviving this copy would return two
            # of the same suggestion. The self-reference guard is belt-and-braces — the critique
            # model already rejects a candidate naming itself — and keeps a malformed artifact from
            # silently erasing the candidate it describes.
            if critique.duplicate_of and critique.duplicate_of != idea.id:
                continue
            if hard_reject:
                continue
            # Everything recoverable routes to one more generator pass instead of a drop: an
            # explicit revise verdict, evidence the critic could not locate (as opposed to evidence
            # that contradicts, which was dropped above), or a reject the critic itself is unsure
            # of. A low-confidence reject is deliberately treated as a revise so the generator gets
            # a chance to answer the objection rather than losing the candidate to a guess.
            needs_revision = (
                critique.verdict is CritiqueVerdict.REVISE
                or critique.evidence_check is CritiqueEvidenceCheck.MISSING
                or (
                    critique.verdict is CritiqueVerdict.REJECT
                    and critique.confidence is CritiqueConfidence.LOW
                )
            )
            # The critique travels with the candidate because the revision turn needs its fix
            # instruction and its preserve list, not just the fact that a rewrite was requested.
            if needs_revision:
                revisions.append((idea, critique))
                continue
            # Keep is checked explicitly rather than treated as the fall-through, so a verdict this
            # policy does not recognise drops out of the round instead of entering the final set
            # unreviewed. Only the review summary is stamped onto the survivor; every generator
            # field stays authoritative, since the critic reviews candidates but does not edit them.
            if critique.verdict is CritiqueVerdict.KEEP:
                kept.append(idea.model_copy(update={"review_summary": critique.review_summary}))
        # An empty revision tuple is the loop's termination signal, so both halves are returned even
        # when one is empty rather than collapsing to a single value.
        return tuple(kept), tuple(revisions)


__all__ = ["SuggestionCritiqueAgent"]
