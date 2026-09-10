"""vidbyte-cli connections status verifies one saved provider connection."""

from __future__ import annotations

from typing import cast

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class ConnectionStatusCommand:
    """Rechecks a named account and refreshes its token when necessary."""

    def register(self, parent: click.Group) -> None:
        # Attaches the provider identity verification command.
        @parent.command(name="status", help="Verify a saved context-provider connection")
        @click.argument("name")
        @click.pass_obj
        def _run(context: ApplicationContext, name: str) -> None:
            # Delegates network and storage behavior to the connection manager.
            self.execute(context, name)

    def execute(self, context: ApplicationContext, name: str) -> None:
        # Resolves a unique name across the selected profile and verifies provider identity.
        profile = context.resolved_config().profile
        metadata = context.connections().status_by_name(profile, name)
        data = cast(dict[str, JsonValue], metadata.model_dump(mode="json"))
        account = metadata.account_label or metadata.account_id
        human = f"{metadata.name} ({metadata.provider.value}) is authenticated as {account}."
        context.output().result(OutputDocument(kind="connections.status", data=data), human)
