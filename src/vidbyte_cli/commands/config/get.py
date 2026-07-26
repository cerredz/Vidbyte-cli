"""FILE: src/vidbyte_cli/commands/config/get.py

PURPOSE: Returns one allow-listed effective non-secret setting for the selected profile,
including its provenance in machine output and optional debug diagnostics.

ROLE IN CODEBASE: The command reads ResolvedConfig through ApplicationContext and delegates
all stream/format policy to OutputManager.

ARCHITECTURE NOTE: `config get` reports effective configuration, so environment overrides
are visible and automation can inspect where a value came from.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ConfigGetCommand.register(parent) -> None: attaches validated field choice.
- ConfigGetCommand.execute(context, field) -> None: renders value and provenance.

WHAT NOT TO DO IN THIS FILE:
1. Do not accept arbitrary keys or return secrets.
2. Do not read configuration files directly.
3. Do not put provenance diagnostics on stdout outside the result document.
4. Do not stringify private exceptions.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from enum import Enum

import click

from ...lib.config import ConfigField
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class ConfigGetCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="get", help="Read an effective CLI configuration value")
        @click.argument("key", type=click.Choice([item.value for item in ConfigField]))
        @click.pass_obj
        def _run(context: ApplicationContext, key: str) -> None:
            self.execute(context, ConfigField(key))

    def execute(self, context: ApplicationContext, field: ConfigField) -> None:
        config = context.resolved_config()
        value = getattr(config, field.value)
        serialized = value.value if isinstance(value, Enum) else value
        source = config.provenance[field]
        if context.options.debug:
            context.output().diagnostic(f"{field.value} source: {source.value}")
        context.output().result(
            OutputDocument(
                kind="config.value",
                data={
                    "profile": config.profile,
                    "key": field.value,
                    "value": serialized,
                    "source": source.value,
                },
            ),
            str(serialized),
        )
