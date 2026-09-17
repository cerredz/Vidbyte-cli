"""Owns generator turns, targeted revisions, and draft-to-idea conversion."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

from ...types.suggestions import (
    SuggestionCandidateBatch,
    SuggestionContextPrimitive,
    SuggestionCritique,
    SuggestionDraft,
    SuggestionIdea,
    SuggestionRequest,
)
from .categories import SuggestionCategories
from .context_bridge import SuggestionContextBridge
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts

AgentCall = Callable[
    [Literal["generator", "critic"], str, SuggestionContextPrimitive, str | None], Awaitable[Any]
]


class SuggestionGeneratorAgent:
    """Builds initial and revision artifacts without owning workflow limits."""

    def __init__(
        self,
        categories: SuggestionCategories,
        prompts: SuggestionPrompts,
        bridge: SuggestionContextBridge,
        handoffs: SuggestionHandoffBuilder,
    ) -> None:
        # Dependencies are injected so the stage can be tested without a provider.
        self._categories = categories
        self._prompts = prompts
        self._bridge = bridge
        self._handoffs = handoffs

    async def generate(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        count: int,
        call: AgentCall,
    ) -> SuggestionCandidateBatch:
        # Initial generation receives only the bridged category and evidence context.
        context = self._bridge.generator(request, category_ids)
        prompt = self._prompts.generator_turn(request.goal, count)
        return cast(
            SuggestionCandidateBatch,
            await call("generator", prompt, context, None),
        )

    def ideas_from_drafts(
        self,
        drafts: SuggestionCandidateBatch | tuple[SuggestionDraft, ...],
        request: SuggestionRequest,
    ) -> tuple[SuggestionIdea, ...]:
        # Assigns stable IDs and deterministic handoffs only after generation completes.
        values = drafts.ideas if isinstance(drafts, SuggestionCandidateBatch) else drafts
        return tuple(
            self._idea_from_draft(
                draft, request, f"idea-{index:03d}", 1, index, "Awaiting independent critique."
            )
            for index, draft in enumerate(values, 1)
        )

    async def revise(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        revisions: tuple[tuple[SuggestionIdea, SuggestionCritique], ...],
        call: AgentCall,
    ) -> tuple[SuggestionIdea, ...]:
        # Revision receives only candidates and critiques selected by the critic stage.
        context = self._bridge.revision(request, category_ids, revisions)
        prompt = self._prompts.revision_turn(request.goal, len(revisions))
        batch = cast(
            SuggestionCandidateBatch,
            await call("generator", prompt, context, None),
        )
        by_id = {idea.id: (idea, critique) for idea, critique in revisions}
        revised: list[SuggestionIdea] = []
        seen_ids: set[str] = set()
        for draft in batch.ideas:
            idea_id = draft.idea_id
            if idea_id is None:
                raise ValueError("revision output must preserve the candidate id")
            if idea_id in seen_ids:
                raise ValueError("revision output repeated a candidate id")
            seen_ids.add(idea_id)
            if idea_id not in by_id:
                raise ValueError("revision output referenced an unknown candidate id")
            original, critique = by_id[idea_id]
            values = draft.model_dump(exclude={"idea_id"})
            for field_name in critique.preserve:
                if hasattr(original, field_name) and field_name in values:
                    values[field_name] = getattr(original, field_name)
            revised_draft = SuggestionDraft.model_validate(values)
            revised.append(
                self._idea_from_draft(
                    revised_draft,
                    request,
                    idea_id,
                    original.revision + 1,
                    original.rank,
                    critique.review_summary,
                )
            )
        by_revision_id = {idea.id: idea for idea in revised}
        return tuple(by_revision_id[idea.id] for idea, _ in revisions if idea.id in by_revision_id)

    def _idea_from_draft(
        self,
        draft: SuggestionDraft,
        request: SuggestionRequest,
        idea_id: str,
        revision: int,
        rank: int,
        review_summary: str,
    ) -> SuggestionIdea:
        # Converts the provider draft while retaining only local identity and execution data.
        values = draft.model_dump(exclude={"idea_id"})
        handoff = self._handoffs.build_draft(draft, request, idea_id, revision)
        return SuggestionIdea(
            **values,
            id=idea_id,
            revision=revision,
            rank=rank,
            review_summary=review_summary,
            handoff=handoff,
        )


__all__ = ["AgentCall", "SuggestionGeneratorAgent"]
