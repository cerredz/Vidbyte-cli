"""Registers local suggestion project creation and catalog listing commands.

Projects are small, credential-free local records that give later suggestion runs a stable
memory scope. This module owns Click parsing and output only; what a project is and how it is
stored belong to `SuggestionProject`.
"""

from __future__ import annotations

from typing import cast

import click
from pydantic import JsonValue

from ....lib.errors.failures import SuggestionProjectInvalid
from ....lib.output import OutputDocument
from ....lib.runtime.context import ApplicationContext as Context
from ....services.suggestions.project import (
    SuggestionProject,
    SuggestionProjectCreateInput,
    SuggestionProjectKey,
)
from .prompts.library import SuggestionHelpLibrary

_HELP = SuggestionHelpLibrary()
_GROUP_HELP = _HELP.load("project_group")
_CREATE_HELP = _HELP.load("project_create")
_LIST_HELP = _HELP.load("project_list")
_KEY_HELP = _HELP.load("project_key")
_TITLE_HELP = _HELP.load("project_title")
_DESCRIPTION_HELP = _HELP.load("project_description")


class SuggestionProjectGroup:
    """Attaches project create and list commands below the suggest group."""

    def register(self, parent: click.Group) -> None:
        # Keeps project verbs together without adding persistence logic to registration.
        project = click.Group(name="project", help=_GROUP_HELP)
        SuggestionProjectCreateCommand().register(project)
        SuggestionProjectListCommand().register(project)
        parent.add_command(project)


class SuggestionProjectCreateCommand:
    """Validates and creates one local suggestion project."""

    def register(self, parent: click.Group) -> None:
        # Click owns required-field errors while the input dataclass owns domain validation.
        @parent.command(name="create", help=_CREATE_HELP)
        @click.option("--key", required=True, help=_KEY_HELP)
        @click.option("--title", required=True, help=_TITLE_HELP)
        @click.option("--description", required=True, help=_DESCRIPTION_HELP)
        @click.pass_obj
        def _create(ctx: Context, key: str, title: str, description: str) -> None:
            self.execute(ctx, key, title, description)

    def execute(self, context: Context, key: str, title: str, description: str) -> None:
        # Every field is validated before the catalog is read, so a bad value writes nothing.
        try:
            request = SuggestionProjectCreateInput(SuggestionProjectKey(key), title, description)
        except (TypeError, ValueError) as error:
            raise SuggestionProjectInvalid(str(error)) from error
        project = SuggestionProject(context.paths()).create(request)
        context.output().result(
            OutputDocument(
                kind="suggestions.project.created", data=project.model_dump(mode="json")
            ),
            f"Created suggestion project '{project.key}'.",
        )


class SuggestionProjectListCommand:
    """Reads and renders the local suggestion project catalog."""

    def register(self, parent: click.Group) -> None:
        # Catalog listing is read-only and remains available without credentials.
        @parent.command(name="list", help=_LIST_HELP)
        @click.pass_obj
        def _list(ctx: Context) -> None:
            self.execute(ctx)

    def execute(self, context: Context) -> None:
        # Renders project summaries only; feedback bodies stay in their own files.
        projects = SuggestionProject(context.paths()).list_projects()
        data: dict[str, JsonValue] = {
            "projects": [cast(JsonValue, project.model_dump(mode="json")) for project in projects]
        }
        human = "\n\n".join(
            f"{project.key}  {project.title}\n  {project.description}" for project in projects
        )
        context.output().result(OutputDocument(kind="suggestions.projects", data=data), human)


__all__ = ["SuggestionProjectGroup"]
