"""vidbyte-cli connections status verifies one saved provider connection."""

from __future__ import annotations

from typing import cast

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext

_STATUS_COMMAND_HELP = (
    "Verify one saved context-provider connection and refresh its token when necessary. "
    "The name argument selects which saved connection to recheck, and it must match exactly "
    "one connection name on the selected profile because ambiguous names are refused. "
    "Verification re-authenticates against the provider and reports current account identity, "
    "workspace labels, and scopes without ever printing token values. "
    "For github connections the result also reports native gh CLI availability, so agents can "
    "see whether deeper native commands are usable alongside the direct read path."
)


class ConnectionStatusCommand:
    """Rechecks a named account and refreshes its token when necessary."""

    def register(self, parent: click.Group) -> None:
        # Attaches the provider identity verification command.
        @parent.command(name="status", help=_STATUS_COMMAND_HELP)
        @click.argument("name")
        @click.pass_obj
        def _run(context: ApplicationContext, name: str) -> None:
            # Delegates network and storage behavior to the connection manager.
            self.execute(context, name)

    def execute(self, context: ApplicationContext, name: str) -> None:
        # Resolves a unique name across the selected profile and verifies provider identity.
        profile = context.resolved_config().profile
        metadata = context.connections().status_by_name(profile, name)
        native = context.connections().native_availability(metadata.provider)
        data = cast(dict[str, JsonValue], metadata.model_dump(mode="json"))
        data["native"] = cast(JsonValue, native)
        account = metadata.account_label or metadata.account_id
        human = f"{metadata.name} ({metadata.provider.value}) is authenticated as {account}."
        context.output().result(OutputDocument(kind="connections.status", data=data), human)
