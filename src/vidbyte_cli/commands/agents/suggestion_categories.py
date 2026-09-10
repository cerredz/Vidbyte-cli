"""Lists the suggestion category registry without calling any model.

The output is driven by the same registry the service uses, so CLI help,
prompt instructions, and schema validation cannot drift apart. No credentials
or provider configuration are needed, which makes this safe for probing.
"""

from __future__ import annotations

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Context
from ...services.suggestions.categories import SCHEMA_VERSION, SuggestionCategories

_COMMAND_HELP = (
    "List every supported suggestion category with its description for callers. "
    "The registry shown here is the exact set the run verb accepts in --category, "
    "so an id missing from this list will fail validation before any model call. "
    "No model is called and no credentials are required, which keeps this safe to "
    "run during setup or in offline environments. Use JSON output when another agent "
    "needs the machine-readable registry."
)


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
            {"id": item.category_id, "description": item.description}
            for item in registry.definitions()
        ]
        data: dict[str, JsonValue] = {"schema_version": SCHEMA_VERSION, "categories": entries}
        lines = [f"{item.category_id}: {item.description}" for item in registry.definitions()]
        context.output().result(
            OutputDocument(kind="suggestions.categories", data=data), "\n".join(lines)
        )
