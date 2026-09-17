"""Registers local suggestion project creation and catalog listing commands.

Projects are small, credential-free local records that give later suggestion runs a stable
memory scope. This module owns Click parsing and output only; JSON persistence stays in the
suggestion project store.
"""

from __future__ import annotations

from typing import cast

import click
from pydantic import JsonValue, ValidationError

from ...lib.errors.failures import (
    StateWriteFailed,
    SuggestionProjectExists,
    SuggestionProjectInvalid,
    SuggestionProjectStateUnreadable,
    SuggestionProjectWriteFailed,
)
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...lib.runtime.context import ApplicationContext as Context
from ...services.suggestions.project_store import (
    ProjectAlreadyExistsError,
    ProjectStateError,
    SuggestionProjectStore,
)

_GROUP_HELP = (
    "Manage small local projects used to scope suggestion memory. The group creates and "
    "lists projects without credentials, provider configuration, or model calls. A project "
    "key becomes the stable selector for later feedback and project-backed suggestion runs. "
    "Project memory is stored beneath the platform-native Vidbyte data directory."
)

_CREATE_HELP = (
    "Create one local project with a stable key, title, and description. The key is the "
    "lowercase identifier used by feedback commands and by `agents suggest run --project`. "
    "Creation fails when the key already exists, so an existing project is never silently "
    "overwritten. The command writes the catalog and the linked memory file without calling "
    "a model or contacting Vidbyte."
)

_LIST_HELP = (
    "List every project currently registered in local suggestion memory. The command reads "
    "the catalog only, so it does not open each feedback file or require credentials. An "
    "empty catalog returns an empty successful result rather than an error. Projects are "
    "sorted by key so human and machine output remain deterministic."
)

_KEY_HELP = (
    "The unique project identifier, using lowercase letters, numbers, hyphens, or "
    "underscores. This value is also used to select the project in feedback and suggestion "
    "run commands. It must begin with a letter or number and be at most 64 characters. "
    "A duplicate or unsafe key fails before any file is written."
)

_TITLE_HELP = (
    "The human-readable project title. Use a short name that helps a parent agent recognize "
    "the project in list output and feedback context. The value is stored exactly after "
    "surrounding whitespace is removed. It is metadata only and does not grant execution "
    "authority to any suggestion."
)

_DESCRIPTION_HELP = (
    "A plain-language description of the project. Explain the scope that future suggestion "
    "runs should understand before interpreting accepted or rejected feedback. The value "
    "is stored exactly after surrounding whitespace is removed and may contain multiple "
    "sentences. It is loaded as context only when a run explicitly supplies --project."
)


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
        # Click owns required-field errors while execute owns domain validation.
        @parent.command(name="create", help=_CREATE_HELP)
        @click.option("--key", required=True, help=_KEY_HELP)
        @click.option("--title", required=True, help=_TITLE_HELP)
        @click.option("--description", required=True, help=_DESCRIPTION_HELP)
        @click.pass_obj
        def _create(ctx: Context, key: str, title: str, description: str) -> None:
            # Delegates to the testable command boundary.
            self.execute(ctx, key, title, description)

    def execute(self, context: ApplicationContext, key: str, title: str, description: str) -> None:
        # Converts store failures into the project-specific repair contract.
        try:
            project = SuggestionProjectStore(context.paths()).create(key, title, description)
        except ProjectAlreadyExistsError as error:
            raise SuggestionProjectExists(key) from error
        except ProjectStateError as error:
            raise SuggestionProjectStateUnreadable("the project catalog is invalid") from error
        except StateWriteFailed as error:
            raise SuggestionProjectWriteFailed(error) from error
        except (OSError, UnicodeError, ValueError, ValidationError) as error:
            raise SuggestionProjectInvalid("key, title, and description must be valid") from error
        context.output().result(
            OutputDocument(
                kind="suggestions.project.created",
                data=project.model_dump(mode="json"),
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
            # Delegates to the testable command boundary.
            self.execute(ctx)

    def execute(self, context: ApplicationContext) -> None:
        # Loads the catalog and renders only project summaries, never feedback bodies.
        try:
            projects = SuggestionProjectStore(context.paths()).list()
        except (OSError, UnicodeError, ValueError, ValidationError) as error:
            raise SuggestionProjectStateUnreadable("the project catalog is invalid") from error
        data: dict[str, JsonValue] = {
            "projects": [cast(JsonValue, project.model_dump(mode="json")) for project in projects]
        }
        human = "\n\n".join(
            f"{project.key}  {project.title}\n  {project.description}" for project in projects
        )
        context.output().result(OutputDocument(kind="suggestions.projects", data=data), human)
