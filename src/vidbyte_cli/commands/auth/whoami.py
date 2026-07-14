"""`vidbyte-cli whoami` — shows which account the stored credentials belong to."""

from __future__ import annotations

import click

from ...lib.errors.cli_error import not_implemented


class WhoamiCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="whoami", help="Show the account behind the stored credentials")
        def _run() -> None:
            self.execute()

    def execute(self) -> None:
        # Will read credentials and call /auth/whoami with them, then print the identity.
        raise not_implemented("'vidbyte-cli whoami'")
