"""Owns the single versioned vocabulary of suggestion categories.

The registry maps each accepted identifier to exactly one authored prompt asset.
Commands, agent context, and result validation all consume this same mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CategoryDefinition:
    """One category identifier and its high-level caller-facing summary."""

    category_id: str
    title: str
    summary: str
    prompt_name: str

    @property
    def description(self) -> str:
        """Keep the public description name readable to existing consumers."""
        return self.summary


class SuggestionCategories:
    """Provides the ordered category registry and one-to-one prompt mapping."""

    def __init__(self) -> None:
        self._definitions = (
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
                "verification",
                "Verification",
                "Test a consequential claim before relying on it.",
                "verification",
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
                "stop_or_defer",
                "Stop or Defer",
                "Stop or postpone work whose present value is insufficient.",
                "stop_or_defer",
            ),
            CategoryDefinition(
                "risk_prevention",
                "Risk Prevention",
                "Prevent a plausible failure with a proportionate guard.",
                "risk_prevention",
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
                "adjacent_opportunity",
                "Adjacent Opportunity",
                "Capture nearby value enabled by current work.",
                "adjacent_opportunity",
            ),
            CategoryDefinition(
                "cross_domain",
                "Cross-Domain",
                "Transfer a useful mechanism from another field.",
                "cross_domain",
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
            CategoryDefinition(
                "goal_clarification",
                "Goal Clarification",
                "Define the intended outcome and how success will be recognized.",
                "goal_clarification",
            ),
            CategoryDefinition(
                "creative_exploration",
                "Creative Exploration",
                "Generate concrete possibilities outside current assumptions.",
                "creative_exploration",
            ),
            CategoryDefinition(
                "delegation",
                "Delegation",
                "Move work to the person or agent best placed to carry it.",
                "delegation",
            ),
            CategoryDefinition(
                "learning",
                "Learning",
                "Build the smallest useful skill or knowledge for an upcoming task.",
                "learning",
            ),
            CategoryDefinition(
                "feedback",
                "Feedback",
                "Seek a specific reaction that could change the work.",
                "feedback",
            ),
            CategoryDefinition(
                "reframing",
                "Reframing",
                "Interpret the problem differently to unlock a better next move.",
                "reframing",
            ),
            CategoryDefinition(
                "prioritization",
                "Prioritization",
                "Choose what deserves attention among competing commitments.",
                "prioritization",
            ),
            CategoryDefinition(
                "immediate_next_steps",
                "Immediate Next Steps",
                "Identify what can be acted on now from the current state.",
                "immediate_next_steps",
            ),
            CategoryDefinition(
                "quick_wins",
                "Quick Wins",
                "Find a small, inexpensive action with useful near-term payoff.",
                "quick_wins",
            ),
            CategoryDefinition(
                "long_term_directions",
                "Long-Term Directions",
                "Consider capabilities or directions worth pursuing over time.",
                "long_term_directions",
            ),
            CategoryDefinition(
                "big_bets",
                "Big Bets",
                "Examine ambitious changes with high upside and meaningful uncertainty.",
                "big_bets",
            ),
            CategoryDefinition(
                "business_growth",
                "Business and Growth",
                "Improve reach, sustainability, revenue, or customer value.",
                "business_growth",
            ),
            CategoryDefinition(
                "product_experience",
                "Product and Experience",
                "Improve what people can use and how it feels to use it.",
                "product_experience",
            ),
            CategoryDefinition(
                "technical_possibilities",
                "Technical Possibilities",
                "Explore what technology could make materially better or possible.",
                "technical_possibilities",
            ),
        )
        self._by_id = {item.category_id: item for item in self._definitions}

    def ids(self) -> tuple[str, ...]:
        """Return identifiers in stable display and selection order."""
        return tuple(item.category_id for item in self._definitions)

    def definitions(self) -> tuple[CategoryDefinition, ...]:
        """Return the immutable registry entries."""
        return self._definitions

    def is_known(self, category_id: str) -> bool:
        """Accept only exact registry identifiers."""
        return category_id in self._by_id

    def require_known(self, category_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Validate selected identifiers without adding inferred categories."""
        unknown = [item for item in category_ids if item not in self._by_id]
        if unknown:
            raise ValueError(f"unknown suggestion categories: {', '.join(sorted(unknown))}")
        if len(set(category_ids)) != len(category_ids):
            raise ValueError("suggestion categories must not contain duplicates")
        return category_ids

    def describe(self, category_id: str) -> CategoryDefinition:
        """Return one already-validated category definition."""
        return self._by_id[category_id]

    def category_prompt_exists(self, prompt_name: str) -> bool:
        """Check that one registry entry resolves to a packaged prompt asset."""
        from .prompts.library import SuggestionPrompts

        try:
            return bool(SuggestionPrompts().category_prompt(prompt_name))
        except (FileNotFoundError, OSError):
            return False

    def prompt_section(self, category_ids: tuple[str, ...] | None = None) -> str:
        """Render exactly the selected prompt assets in the selected order."""
        from .prompts.library import SuggestionPrompts

        selected = (
            self._definitions
            if not category_ids
            else tuple(self._by_id[item] for item in category_ids)
        )
        prompts = SuggestionPrompts()
        return "\n\n".join(prompts.category_prompt(item.prompt_name) for item in selected)


__all__ = ["SCHEMA_VERSION", "CategoryDefinition", "SuggestionCategories"]
