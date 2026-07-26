"""FILE: src/vidbyte_cli/commands/config/set.py

PURPOSE: Validates and atomically writes one allow-listed non-secret profile setting.

ROLE IN CODEBASE: This thin command delegates schema, legacy-config compatibility, and
write mechanics to ConfigStore, then emits a versioned result.

ARCHITECTURE NOTE: Values remain strings at Click's boundary and are parsed by ProfileConfig,
keeping one canonical validation path for command, environment, and persisted data.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ConfigSetCommand.register(parent) -> None: attaches field/value arguments.
- ConfigSetCommand.execute(context, field, value) -> None: migrates and persists.

WHAT NOT TO DO IN THIS FILE:
1. Do not add arbitrary keys or secret fields.
2. Do not write JSON or create directories directly.
3. Do not silently overwrite invalid/future configuration.
4. Do not mutate a profile other than the selected root profile.

TESTS: No feature tests are added under the approved no-tests workflow.
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

    def execute(
        self,
        context: ApplicationContext,
        field: ConfigField,
        value: str,
    ) -> None:
        updated = context.config_store().set(field, value, context.options.profile)
        saved = getattr(updated, field.value)
        serialized = saved.value if isinstance(saved, Enum) else saved
        context.output().result(
            OutputDocument(
                kind="config.updated",
                data={
                    "profile": context.options.profile,
                    "key": field.value,
                    "value": serialized,
                },
            ),
            f"Set {field.value} for profile '{context.options.profile}' to {serialized}.",
        )
