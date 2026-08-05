"""`vidbyte-cli logout` — removes stored credentials from this machine.

Logout is a desired state, not an action that must have had something to undo: an
already-logged-out profile succeeds, so a cleanup script can run it unconditionally.
"""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class LogoutCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="logout", help="Remove stored Vidbyte credentials from this machine")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Scoped to the selected profile and API host: logging out of staging must leave the
        # production credential alone.
        config = context.resolved_config()
        removed = context.credential_store().clear(config.profile, config.api_url)
        context.output().result(
            OutputDocument(
                kind="auth.logout",
                data={
                    "profile": config.profile,
                    "api_url": config.api_url,
                    "removed": removed,
                },
            ),
            (
                f"Removed credentials for profile '{config.profile}'."
                if removed
                else f"Profile '{config.profile}' was already logged out."
            ),
        )
