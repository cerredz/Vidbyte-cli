"""`vidbyte-cli config set <key> <value>` — writes a non-secret CLI setting.

The value stays a string across Click's boundary and is parsed by `ProfileConfig`, so the
command line, the environment, and the persisted document all validate the same way.
"""

from __future__ import annotations

from enum import Enum

import click

from ...lib.config import ConfigField
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class ConfigSetCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="set", help="Write a CLI configuration value")
        @click.argument("key", type=click.Choice([item.value for item in ConfigField]))
        @click.argument("value")
        @click.pass_obj
        def _run(context: ApplicationContext, key: str, value: str) -> None:
            self.execute(context, ConfigField(key), value)

    def execute(self, context: ApplicationContext, field: ConfigField, value: str) -> None:
        profile = context.options.profile
        updated = context.config_store().set(field, value, profile)
        # Echo what was stored, not what was typed: normalization may have changed it.
        saved = getattr(updated, field.value)
        serialized = saved.value if isinstance(saved, Enum) else saved
        context.output().result(
            OutputDocument(
                kind="config.updated",
                data={"profile": profile, "key": field.value, "value": serialized},
            ),
            f"Set {field.value} for profile '{profile}' to {serialized}.",
        )
