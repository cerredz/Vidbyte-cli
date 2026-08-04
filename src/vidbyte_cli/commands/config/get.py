"""`vidbyte-cli config get <key>` — reads a non-secret CLI setting."""

from __future__ import annotations

import click

from ...lib.errors.failures import NotImplementedFeature


class ConfigGetCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="get", help="Read a CLI configuration value")
        @click.argument("key")
        def _run(key: str) -> None:
            self.execute(key)

    def execute(self, key: str) -> None:
        # Will read the value from the config store and print it.
        raise NotImplementedFeature("'vidbyte-cli config get'")
