"""Runs one isolated generator context per selected category in parallel."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import Literal

from ...types.suggestions import (
    SuggestionAgentContext,
    SuggestionCandidateBatch,
    SuggestionDraft,
    SuggestionRequest,
)
from .categories import SuggestionCategories
from .prompts.library import SuggestionPrompts

AgentCall = Callable[
    [Literal["generator", "critic"], str, SuggestionAgentContext, str | None],
    Awaitable[SuggestionCandidateBatch],
]


class ExtraComputeService:
    """Fans out focused category windows and combines their typed drafts stably."""

    def __init__(self, categories: SuggestionCategories, prompts: SuggestionPrompts) -> None:
        self._categories = categories
        self._prompts = prompts

    async def generate(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        pool_size: int,
        call: AgentCall,
    ) -> tuple[SuggestionDraft, ...]:
        per_category = max(1, math.ceil(pool_size / len(category_ids)))

        async def run_one(category_id: str) -> SuggestionCandidateBatch:
            context = SuggestionAgentContext.for_stage(
                request.context, self._categories.prompt_section((category_id,))
            )
            prompt = self._prompts.generator_turn(request.goal, per_category)
            return await call("generator", prompt, context, None)

        batches = await asyncio.gather(*(run_one(category) for category in category_ids))
        drafts = tuple(draft for batch in batches for draft in batch.ideas)
        return drafts[:pool_size]


__all__ = ["AgentCall", "ExtraComputeService"]
