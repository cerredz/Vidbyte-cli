"""`vidbyte-cli logout` — removes stored credentials from this machine."""

from __future__ import annotations

import click

from ...lib.errors.failures import NotImplementedFeature


class LogoutCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="logout", help="Remove stored Vidbyte credentials from this machine")
        def _run() -> None:
            self.execute()

    def execute(self) -> None:
        # Will clear the credential store (idempotent) and confirm to the user.
        raise NotImplementedFeature("'vidbyte-cli logout'")
