"""vidbyte-cli connections logout removes one local named connection."""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class ConnectionLogoutCommand:
    """Revokes where possible and removes local keyring and metadata state."""

    def register(self, parent: click.Group) -> None:
        # Attaches the named connection cleanup command.
        @parent.command(name="logout", help="Remove a saved context-provider connection")
        @click.argument("name")
        @click.pass_obj
        def _run(context: ApplicationContext, name: str) -> None:
            # Delegates provider revocation and local removal to the manager.
            self.execute(context, name)

    def execute(self, context: ApplicationContext, name: str) -> None:
        # Local removal succeeds even if provider-side revocation cannot be reached.
        profile = context.resolved_config().profile
        context.connections().logout_by_name(profile, name)
        context.output().result(
            OutputDocument(
                kind="connections.logout",
                data={"profile": profile, "name": name, "removed": True},
            ),
            f"Removed context connection '{name}'.",
        )
