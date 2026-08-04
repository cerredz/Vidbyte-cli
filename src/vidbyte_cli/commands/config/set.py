"""`vidbyte-cli config set <key> <value>` — writes a non-secret CLI setting."""

from __future__ import annotations

import click

from ...lib.errors.failures import NotImplementedFeature


class ConfigSetCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="set", help="Write a CLI configuration value")
        @click.argument("key")
        @click.argument("value")
        def _run(key: str, value: str) -> None:
            self.execute(key, value)

    def execute(self, key: str, value: str) -> None:
        # Will persist the key/value pair to the config store.
        raise NotImplementedFeature("'vidbyte-cli config set'")
