"""vidbyte-cli connections read performs bounded provider resource reads."""

from __future__ import annotations

import json
from typing import cast

import click
from pydantic import JsonValue, ValidationError

from ...lib.errors.failures import ConnectionProtocolError
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.connection import ConnectionProvider, ConnectionRead, ConnectionResource


class ConnectionReadCommand:
    """Reads one repository, pull request, Slack channel, or Drive file."""

    def register(self, parent: click.Group) -> None:
        # Adds a closed provider/resource surface so arbitrary URLs never reach adapters.
        @parent.command(name="read", help="Read one bounded provider resource")
        @click.argument("provider", type=click.Choice(ConnectionProvider.cli_choices()))
        @click.argument(
            "resource_type",
            type=click.Choice(["repo", "pull-request", "channel", "file"]),
        )
        @click.argument("identifier")
        @click.option(
            "--connection",
            "connection_name",
            default=None,
            help="Named connection to use.",
        )
        @click.option(
            "--number",
            type=click.IntRange(min=1),
            default=None,
            help="Pull request number when reading a GitHub pull request.",
        )
        @click.option(
            "--limit",
            type=click.IntRange(min=1, max=100),
            default=50,
            show_default=True,
            help="Maximum Slack messages to return.",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, provider: str, resource_type: str, identifier: str, connection_name: str | None, number: int | None, limit: int) -> None:  # fmt: skip  # noqa: E501
            # Click owns primitive validation; the command validates provider-specific meaning.
            self.execute(
                context,
                provider,
                resource_type,
                identifier,
                connection_name,
                number,
                limit,
            )

    def execute(self, context: ApplicationContext, provider: str, resource_type: str, identifier: str, connection_name: str | None, number: int | None, limit: int) -> None:  # fmt: skip  # noqa: E501
        # Builds one typed resource before resolving credentials or making a request.
        typed_provider = ConnectionProvider.from_cli(provider)
        self._validate_resource_type(typed_provider, resource_type)
        try:
            resource = ConnectionResource(
                provider=typed_provider,
                resource_type=resource_type,  # type: ignore[arg-type]
                identifier=identifier,
                number=number,
                limit=limit,
            )
        except ValidationError as error:
            raise ConnectionProtocolError(provider, error) from error
        name = connection_name or typed_provider.value
        result = context.connections().read(
            context.resolved_config().profile,
            typed_provider,
            name,
            resource,
        )
        self._render(context, result)

    def _validate_resource_type(self, provider: ConnectionProvider, resource_type: str) -> None:
        # Rejects a syntactically valid but provider-incompatible resource before network access.
        allowed = {
            ConnectionProvider.GITHUB: {"repo", "pull-request"},
            ConnectionProvider.SLACK: {"channel"},
            ConnectionProvider.GOOGLE_DRIVE: {"file"},
        }
        if resource_type not in allowed[provider]:
            raise ConnectionProtocolError(
                provider.value,
                ValueError("resource type is unsupported"),
            )

    def _render(self, context: ApplicationContext, result: ConnectionRead) -> None:
        # Emits provider data in a stable envelope and a readable terminal representation.
        data = cast(dict[str, JsonValue], result.model_dump(mode="json"))
        human = json.dumps(result.data, indent=2, sort_keys=True, ensure_ascii=False)
        context.output().result(OutputDocument(kind="connections.read", data=data), human)
