"""Owns the versioned category registry for the suggestion agent.

One module defines the vocabulary so CLI validation, prompt instructions, and
schema checks cannot drift apart. Categories describe what the generator should
look for; horizon, relationship, and readiness stay separate dimensions in types.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CategoryDefinition:
    """One category id plus the instruction the generator receives for it."""

    category_id: str
    description: str
    guidance: str


class SuggestionCategories:
    """Registry of the 17 v1 categories with validation and prompt rendering."""

    def __init__(self) -> None:
        # Fixed at construction so every caller in one process sees the same order.
        self._definitions: tuple[CategoryDefinition, ...] = (
            CategoryDefinition(
                "continuation",
                "The next concrete action in the current plan.",
                "Prefer the smallest unblocked step that advances the stated goal.",
            ),
            CategoryDefinition(
                "prerequisite",
                "Something that must exist before planned work can succeed.",
                "Name the missing capability and the work it unblocks.",
            ),
            CategoryDefinition(
                "completion",
                "An unfinished obligation needed to close the current task.",
                "Tie the idea to an explicit loose end in the supplied context.",
            ),
            CategoryDefinition(
                "bottleneck",
                "A constraint whose removal would accelerate progress.",
                "Quantify the constraint in time, tokens, or waiting where possible.",
            ),
            CategoryDefinition(
                "verification",
                "A consequential assumption, implementation, or result to check.",
                "State the claim, the check, and what changes if it fails.",
            ),
            CategoryDefinition(
                "experiment",
                "A small test that resolves an important uncertainty.",
                "Bound the test under a day and name the decision it informs.",
            ),
            CategoryDefinition(
                "investigation",
                "Missing knowledge worth gathering before deciding.",
                "Name the question, the cheapest source, and the stopping rule.",
            ),
            CategoryDefinition(
                "alternative",
                "A materially different route to the same goal.",
                "Contrast with the current route on cost, risk, and reversibility.",
            ),
            CategoryDefinition(
                "simplification",
                "A way to reduce scope, complexity, or effort.",
                "Name what is removed and what is preserved.",
            ),
            CategoryDefinition(
                "stop_or_defer",
                "Work that should stop or wait, with a reason and revisit rule.",
                "Give the reconsideration condition, not just the pause.",
            ),
            CategoryDefinition(
                "risk_prevention",
                "A concrete action to prevent a plausible problem.",
                "Name the failure mode, its likelihood, and the guard.",
            ),
            CategoryDefinition(
                "leverage",
                "Work that benefits several future tasks, such as reuse.",
                "List at least two future consumers of the artifact.",
            ),
            CategoryDefinition(
                "strategy",
                "A broader direction or investment choice.",
                "Connect the direction to the goal and its opportunity cost.",
            ),
            CategoryDefinition(
                "adjacent_opportunity",
                "A nearby opportunity enabled by current work.",
                "Explain why now is cheaper than later.",
            ),
            CategoryDefinition(
                "cross_domain",
                "A useful approach borrowed from another field.",
                "Name the source field and the mapping, not just the analogy.",
            ),
            CategoryDefinition(
                "preparation",
                "Work that prepares for an anticipated event.",
                "Name the event, its trigger, and the readiness check.",
            ),
            CategoryDefinition(
                "coordination",
                "A needed ownership, sequencing, or dependency decision.",
                "Name the owners and the decision that unblocks sequencing.",
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
        # Renders only the selected categories, or the whole registry when unrestricted.
        selected = (
            self._definitions
            if not category_ids
            else tuple(self._by_id[item] for item in category_ids)
        )
        lines = [f"- {item.category_id}: {item.description} {item.guidance}" for item in selected]
        return "\n".join(lines)
