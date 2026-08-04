"""`vidbyte-cli login` — stores the user's Vidbyte API key for later commands."""

from __future__ import annotations

import click

from ...lib.errors.failures import NotImplementedFeature


class LoginCommand:
    def register(self, parent: click.Group) -> None:
        # Attaches `login` to the root program.
        @parent.command(name="login", help="Authenticate the CLI with your Vidbyte API key")
        @click.option("--api-key", "api_key", default=None, help="API key (else prompt / env)")
        def _run(api_key: str | None) -> None:
            self.execute(api_key)

    def execute(self, api_key: str | None) -> None:
        # Will resolve the key (flag > env > hidden prompt), verify it via /auth/whoami, then
        # persist it — verify-before-write so an invalid key never lands on disk.
        raise NotImplementedFeature("'vidbyte-cli login'")
