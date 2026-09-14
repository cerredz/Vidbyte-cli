"""Loads the suggestion agent's versioned category definitions.

Each category is authored as a reviewable Markdown prompt asset and parsed
into one immutable definition. The registry is the shared source for caller
inspection, multi-category selection, prompt context, and result validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

SCHEMA_VERSION = 1

_CATEGORY_IDS = (
    "continuation",
    "prerequisite",
    "completion",
    "bottleneck",
    "verification",
    "experiment",
    "investigation",
    "alternative",
    "simplification",
    "stop_or_defer",
    "risk_prevention",
    "leverage",
    "strategy",
    "adjacent_opportunity",
    "cross_domain",
    "preparation",
    "coordination",
)
_REQUIRED_SECTIONS = ("Description", "Goal", "Intent", "Timeline", "Checklist", "Cautions")
_CATEGORY_PACKAGE = "vidbyte_cli.services.suggestions.prompts.categories"


@dataclass(frozen=True, slots=True)
class CategoryDefinition:
    """One fully authored suggestion category and its model-facing source."""

    category_id: str
    title: str
    description: str
    goal: str
    intent: str
    timeline: str
    checklist: tuple[str, ...]
    cautions: str
    prompt: str

    def __post_init__(self) -> None:
        scalar_fields = (
            self.category_id,
            self.title,
            self.description,
            self.goal,
            self.intent,
            self.timeline,
            self.cautions,
            self.prompt,
        )
        if any(not isinstance(value, str) or not value.strip() for value in scalar_fields):
            raise ValueError("Category definition fields must be non-empty strings.")
        if not self.checklist or any(not item.strip() for item in self.checklist):
            raise ValueError("Category definitions require a non-empty checklist.")


class CategoryDefinitionLibrary:
    """Parses detailed category Markdown from installed package resources."""

    def load(self, category_id: str) -> CategoryDefinition:
        source = resources.files(_CATEGORY_PACKAGE).joinpath(f"{category_id}.md")
        prompt = source.read_text(encoding="utf-8").strip()
        title, sections = self._sections(prompt)
        missing = tuple(name for name in _REQUIRED_SECTIONS if not sections.get(name))
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"Category {category_id!r} is missing sections: {names}.")
        checklist = tuple(
            line.removeprefix("- ").strip()
            for line in sections["Checklist"].splitlines()
            if line.strip().startswith("- ")
        )
        return CategoryDefinition(
            category_id=category_id,
            title=title,
            description=sections["Description"],
            goal=sections["Goal"],
            intent=sections["Intent"],
            timeline=sections["Timeline"],
            checklist=checklist,
            cautions=sections["Cautions"],
            prompt=prompt,
        )

    def _sections(self, prompt: str) -> tuple[str, dict[str, str]]:
        title = ""
        active = ""
        sections: dict[str, list[str]] = {}
        for line in prompt.splitlines():
            if line.startswith("# ") and not title:
                title = line[2:].strip()
                continue
            if line.startswith("## "):
                active = line[3:].strip()
                sections.setdefault(active, [])
                continue
            if active:
                sections[active].append(line)
        normalized = {name: "\n".join(lines).strip() for name, lines in sections.items()}
        return title, normalized


class SuggestionCategories:
    """Registry of the 17 v1 categories in stable presentation order."""

    def __init__(self) -> None:
        library = CategoryDefinitionLibrary()
        self._definitions = tuple(library.load(category_id) for category_id in _CATEGORY_IDS)
        self._by_id = {item.category_id: item for item in self._definitions}

    def ids(self) -> tuple[str, ...]:
        return tuple(item.category_id for item in self._definitions)

    def definitions(self) -> tuple[CategoryDefinition, ...]:
        return self._definitions

    def is_known(self, category_id: str) -> bool:
        return category_id in self._by_id

    def require_known(self, category_ids: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [item for item in category_ids if item not in self._by_id]
        if unknown:
            raise ValueError(f"unknown suggestion categories: {', '.join(sorted(unknown))}")
        return category_ids

    def describe(self, category_id: str) -> CategoryDefinition:
        return self._by_id[category_id]

    def prompt_section(self, category_ids: tuple[str, ...] | None = None) -> str:
        selected = (
            self._definitions
            if not category_ids
            else tuple(self._by_id[item] for item in category_ids)
        )
        return "\n\n".join(item.prompt for item in selected)


__all__ = ["CategoryDefinition", "CategoryDefinitionLibrary", "SuggestionCategories"]
