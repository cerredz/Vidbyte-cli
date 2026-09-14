"""Validates eligibility, ranking, and redundancy for candidate ideas.

Exact duplicates are removed in code by normalized title; semantic overlap is
left to the critic in the service. Selection never invents evidence: every
evidence ref must already exist in the run's context manifest.
"""

from __future__ import annotations

from ...types.suggestions import SuggestionIdea


class SuggestionSelection:
    """Applies deterministic selection rules over reviewed candidates."""

    def __init__(self) -> None:
        # Stateless across runs; all inputs arrive per call.
        pass

    def validate_evidence(
        self, ideas: tuple[SuggestionIdea, ...], allowed: set[str]
    ) -> tuple[SuggestionIdea, ...]:
        # Drops ideas that cite refs the manifest never issued.
        return tuple(idea for idea in ideas if set(idea.evidence_refs) <= allowed)

    def deduplicate(self, ideas: tuple[SuggestionIdea, ...]) -> tuple[SuggestionIdea, ...]:
        # Keeps the first idea per normalized title so ordering stays stable.
        seen: set[str] = set()
        kept: list[SuggestionIdea] = []
        for idea in ideas:
            key = " ".join(idea.title.lower().split())
            if key in seen:
                continue
            seen.add(key)
            kept.append(idea)
        return tuple(kept)

    def suppress_rejected(
        self, ideas: tuple[SuggestionIdea, ...], rejected: tuple[str, ...]
    ) -> tuple[SuggestionIdea, ...]:
        # Removes ideas whose title or summary echoes caller-rejected directions.
        needles = [item.lower() for item in rejected if item.strip()]
        if not needles:
            return ideas
        kept: list[SuggestionIdea] = []
        for idea in ideas:
            haystack = f"{idea.title} {idea.summary}".lower()
            if any(needle and needle in haystack for needle in needles):
                continue
            kept.append(idea)
        return tuple(kept)

    def rank(self, ideas: tuple[SuggestionIdea, ...], limit: int) -> tuple[SuggestionIdea, ...]:
        # Reassigns rank sequentially after trimming to the requested maximum.
        return tuple(
            idea.model_copy(update={"rank": index}) for index, idea in enumerate(ideas[:limit], 1)
        )

    def coverage(self, ideas: tuple[SuggestionIdea, ...]) -> dict[str, int]:
        # Counts primary categories represented in the final slate.
        counts: dict[str, int] = {}
        for idea in ideas:
            counts[idea.primary_category] = counts.get(idea.primary_category, 0) + 1
        return counts
