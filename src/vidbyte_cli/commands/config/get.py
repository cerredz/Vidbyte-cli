"""`vidbyte-cli config get <key>` — reads a non-secret CLI setting.

It reports the *effective* value, not the stored one, so an environment override is visible
rather than mysterious. Machine output carries the provenance alongside it.
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
        # Human output is the bare value so `$(vidbyte-cli config get api_url)` is usable.
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
