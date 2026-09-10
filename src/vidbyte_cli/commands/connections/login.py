"""vidbyte-cli connections login authenticates a context provider.

Interactive progress is written to stderr; the final result contains only non-secret connection
metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.connection import ConnectionMetadata, ConnectionProvider


class ConnectionLoginCommand:
    """Runs one provider's interactive OAuth connection flow."""

    def register(self, parent: click.Group) -> None:
        # Adds provider choice and non-secret client configuration to the command surface.
        @parent.command(name="login", help="Authenticate a GitHub, Slack, or Google Drive account")
        @click.argument("provider", type=click.Choice(ConnectionProvider.cli_choices()))
        @click.option("--name", default=None, help="Store this account under a named connection.")
        @click.option(
            "--scope",
            "scopes",
            multiple=True,
            help="Request one provider scope; repeat for multiple scopes.",
        )
        @click.option(
            "--client-secrets",
            type=click.Path(path_type=Path, dir_okay=False, readable=True),
            default=None,
            help="Google installed-app client JSON path.",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, provider: str, name: str | None, scopes: tuple[str, ...], client_secrets: Path | None) -> None:  # fmt: skip  # noqa: E501
            # Click owns parsing; execution stays on the command class.
            self.execute(context, provider, name, scopes, client_secrets)

    def execute(self, context: ApplicationContext, provider: str, name: str | None, scopes: tuple[str, ...], client_secrets_path: Path | None) -> None:  # fmt: skip  # noqa: E501
        # Saves a verified provider token only after the complete OAuth flow succeeds.
        if context.options.no_input:
            raise click.UsageError("Interactive provider login cannot run with --no-input.")
        typed_provider = ConnectionProvider.from_cli(provider)
        connection_name = name or typed_provider.value
        metadata = context.connections().login(
            typed_provider,
            connection_name,
            scopes,
            client_secrets_path,
        )
        data = cast(dict[str, JsonValue], metadata.model_dump(mode="json"))
        human = self._human(metadata)
        context.output().result(OutputDocument(kind="connections.login", data=data), human)

    def _human(self, metadata: ConnectionMetadata) -> str:
        # Renders only metadata fields selected by the typed connection model.
        provider = metadata.provider.value
        name = metadata.name
        account = metadata.account_label or metadata.account_id
        return f"Authenticated {provider} connection '{name}' for account '{account}'."
