"""vidbyte-cli connections list displays secret-free local connection metadata."""

from __future__ import annotations

from typing import cast

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.connection import ConnectionMetadata


class ConnectionListCommand:
    """Lists named connections without touching provider APIs or token secrets."""

    def register(self, parent: click.Group) -> None:
        # Attaches the offline metadata list command.
        @parent.command(name="list", help="List saved context-provider connections")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            # Delegates list behavior to the command's execution method.
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Metadata list is deliberately offline and does not unlock the keyring.
        config = context.resolved_config()
        entries = context.connections().list(config.profile)
        serialized = [cast(JsonValue, entry.model_dump(mode="json")) for entry in entries]
        human = "\n".join(self._line(entry) for entry in entries)
        human = human or "No context-provider connections are saved."
        context.output().result(
            OutputDocument(kind="connections.list", data={"connections": serialized}),
            human,
        )

    def _line(self, entry: ConnectionMetadata) -> str:
        # Formats one non-secret metadata record for a terminal.
        account = entry.account_label or entry.account_id
        return f"{entry.name} ({entry.provider.value}): {account}"
