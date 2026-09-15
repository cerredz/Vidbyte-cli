"""Lists or expands the suggestion category registry without model work."""

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
from ....services.suggestions.prompts.library import SuggestionPrompts
from .prompts.library import SuggestionHelpLibrary

_COMMAND_HELP = SuggestionHelpLibrary().load("categories")
_VIEW_ALL_HELP = SuggestionHelpLibrary().load("view_all")
_VIEW_HELP = SuggestionHelpLibrary().load("view")


class SuggestionCategoriesCommand:
    """Renders summaries for all categories or the full definition for one category."""

    def register(self, parent: click.Group) -> None:
        # The Choice is registry-owned, so CLI validation and displayed ids cannot drift.
        @parent.command(name="categories", help=_COMMAND_HELP)
        @click.option("--view-all", is_flag=True, help=_VIEW_ALL_HELP)
        @click.option(
            "--view",
            "view_id",
            type=click.Choice(SuggestionCategories().ids()),
            default=None,
            help=_VIEW_HELP,
        )
        @click.pass_obj
        def _categories(ctx: Context, view_all: bool, view_id: str | None) -> None:
            self.execute(ctx, view_all=view_all, view_id=view_id)

    def execute(self, context: Context, *, view_all: bool, view_id: str | None) -> None:
        if view_all and view_id:
            raise click.UsageError("--view-all and --view cannot be used together.")
        registry = SuggestionCategories()
        prompts = SuggestionPrompts()
        if view_id:
            definition = registry.describe(view_id)
            entries: list[JsonValue] = [
                self._expanded(definition, prompts.category_prompt(definition.prompt_name))
            ]
            human = prompts.category_prompt(definition.prompt_name)
        else:
            entries = [self._summary(item) for item in registry.definitions()]
            human = "\n\n".join(self._human_summary(item) for item in registry.definitions())
        data: dict[str, JsonValue] = {
            "schema_version": SCHEMA_VERSION,
            "view": "category" if view_id else "all",
            "categories": entries,
        }
        context.output().result(OutputDocument(kind="suggestions.categories", data=data), human)

    def _summary(self, item: CategoryDefinition) -> dict[str, JsonValue]:
        return {"id": item.category_id, "title": item.title, "summary": item.summary}

    def _expanded(self, item: CategoryDefinition, prompt: str) -> dict[str, JsonValue]:
        return {
            "id": item.category_id,
            "title": item.title,
            "summary": item.summary,
            "prompt": prompt,
        }

    def _human_summary(self, item: CategoryDefinition) -> str:
        return f"{item.category_id} — {item.title}: {item.summary}"


__all__ = ["SuggestionCategoriesCommand"]
