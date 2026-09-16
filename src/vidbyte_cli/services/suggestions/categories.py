"""Owns the versioned category registry for the suggestion agent.

One module defines the vocabulary so CLI validation, prompt instructions, and
schema checks cannot drift apart. Full model-facing guidance lives in packaged
Markdown assets; this module owns identifiers, summaries, and asset mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CategoryDefinition:
    """One category identifier, summary, and packaged guidance asset."""

    category_id: str
    title: str
    summary: str
    prompt_name: str

    @property
    def description(self) -> str:
        # Preserves the public description name used by the category command.
        return self.summary


class SuggestionCategories:
    """Registry of the 14 v1 categories with validation and prompt rendering."""

    def __init__(self) -> None:
        # Fixed at construction so every caller in one process sees the same order.
        self._definitions: tuple[CategoryDefinition, ...] = (
            CategoryDefinition(
                "continuation",
                "Continuation",
                "Advance an accepted plan with its next bounded step.",
                "continuation",
            ),
            CategoryDefinition(
                "prerequisite",
                "Prerequisite",
                "Create or secure a condition required by intended work.",
                "prerequisite",
            ),
            CategoryDefinition(
                "completion",
                "Completion",
                "Close a specific unfinished obligation in the current task.",
                "completion",
            ),
            CategoryDefinition(
                "bottleneck",
                "Bottleneck",
                "Relieve the constraint that limits useful progress.",
                "bottleneck",
            ),
            CategoryDefinition(
                "experiment",
                "Experiment",
                "Run a bounded test that can change a decision.",
                "experiment",
            ),
            CategoryDefinition(
                "investigation",
                "Investigation",
                "Gather the smallest reliable evidence needed for a decision.",
                "investigation",
            ),
            CategoryDefinition(
                "alternative",
                "Alternative",
                "Compare a materially different route to the same goal.",
                "alternative",
            ),
            CategoryDefinition(
                "simplification",
                "Simplification",
                "Remove complexity while preserving essential value.",
                "simplification",
            ),
            CategoryDefinition(
                "leverage",
                "Leverage",
                "Create one asset that benefits several credible future tasks.",
                "leverage",
            ),
            CategoryDefinition(
                "strategy",
                "Strategy",
                "Choose a broader direction that coordinates several actions.",
                "strategy",
            ),
            CategoryDefinition(
                "long_term_suggestions",
                "Long-Term Suggestions",
                "Develop durable directions across a 3-6 month or 2 year+ horizon.",
                "long_term_suggestions",
            ),
            CategoryDefinition(
                "adjacent_opportunity",
                "Adjacent Opportunity",
                "Capture nearby value enabled by current work.",
                "adjacent_opportunity",
            ),
            CategoryDefinition(
                "preparation",
                "Preparation",
                "Build readiness for an anticipated event or demand.",
                "preparation",
            ),
            CategoryDefinition(
                "coordination",
                "Coordination",
                "Resolve ownership, sequencing, or dependency alignment.",
                "coordination",
            ),
        )
        self._by_id: dict[str, CategoryDefinition] = {
            item.category_id: item for item in self._definitions
        }

    def ids(self) -> tuple[str, ...]:
        # Order is the registry order, which is also the categories-command order.
        return tuple(item.category_id for item in self._definitions)

    def definitions(self) -> tuple[CategoryDefinition, ...]:
        # Returns the owned tuple so callers cannot mutate the registry.
        return self._definitions

    def is_known(self, category_id: str) -> bool:
        # Exact match only; no aliases, prefixes, or case folding are accepted.
        return category_id in self._by_id

    def require_known(self, category_ids: tuple[str, ...]) -> tuple[str, ...]:
        # Raises ValueError so the command layer can convert it to a typed failure.
        unknown = [item for item in category_ids if item not in self._by_id]
        if unknown:
            raise ValueError(f"unknown suggestion categories: {', '.join(sorted(unknown))}")
        return category_ids

    def describe(self, category_id: str) -> CategoryDefinition:
        # Callers must have validated first; unknown ids are a programming error here.
        return self._by_id[category_id]

    def prompt_section(self, category_ids: tuple[str, ...] | None = None) -> str:
        # Renders only the selected category assets, or the whole registry when unrestricted.
        from .prompts.library import SuggestionPrompts

        selected = (
            self._definitions
            if not category_ids
            else tuple(self._by_id[item] for item in category_ids)
        )
        prompts = SuggestionPrompts()
        return "\n\n".join(prompts.category_prompt(item.prompt_name) for item in selected)
