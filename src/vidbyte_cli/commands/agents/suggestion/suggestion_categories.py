"""Lists the suggestion category registry without calling any model.

The output is driven by the same registry the service uses, so CLI help,
prompt instructions, and schema validation cannot drift apart. No credentials
or provider configuration are needed, which makes this safe for probing.
"""

from __future__ import annotations

import click
from pydantic import JsonValue

from ....lib.output import OutputDocument
from ....lib.runtime.context import ApplicationContext as Context
from ....services.suggestions.categories import (
    SCHEMA_VERSION,
    CategoryDefinition,
    SuggestionCategories,
)
from .prompts.library import SuggestionHelpLibrary

_COMMAND_HELP = SuggestionHelpLibrary().load("categories")


class SuggestionCategoriesCommand:
    """Renders category ids and descriptions in human and machine forms."""

    def register(self, parent: click.Group) -> None:
        # Attaches categories as a credential-free read verb on the suggest group.
        @parent.command(name="categories", help=_COMMAND_HELP)
        @click.pass_obj
        def _categories(ctx: Context) -> None:
            # Delegates to the execution method for direct testing.
            self.execute(ctx)

    def execute(self, context: Context) -> None:
        # Emits the registry envelope plus a one-line-per-category human view.
        registry = SuggestionCategories()
        entries: list[JsonValue] = [
            {
                "id": item.category_id,
                "title": item.title,
                "description": item.description,
                "goal": item.goal,
                "intent": item.intent,
                "timeline": item.timeline,
                "checklist": list(item.checklist),
                "cautions": item.cautions,
            }
            for item in registry.definitions()
        ]
        data: dict[str, JsonValue] = {"schema_version": SCHEMA_VERSION, "categories": entries}
        lines = [self._human(item) for item in registry.definitions()]
        context.output().result(
            OutputDocument(kind="suggestions.categories", data=data), "\n".join(lines)
        )

    def _human(self, item: CategoryDefinition) -> str:
        checks = "\n".join(f"  - {check}" for check in item.checklist)
        return (
            f"{item.category_id} — {item.title}\n"
            f"  Description: {item.description}\n"
            f"  Goal: {item.goal}\n"
            f"  Intent: {item.intent}\n"
            f"  Timeline: {item.timeline}\n"
            f"  Checklist:\n{checks}\n"
            f"  Cautions: {item.cautions}"
        )
