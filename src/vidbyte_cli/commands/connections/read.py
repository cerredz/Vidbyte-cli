"""vidbyte-cli connections read performs bounded provider resource reads."""

from __future__ import annotations

import json
from typing import cast

import click
from pydantic import JsonValue, ValidationError

from ...lib.errors.failures import ConnectionProtocolError
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.connection import ConnectionProvider, ConnectionRead, ConnectionResource, ReadVia

_READ_COMMAND_HELP = (
    "Read one bounded provider resource as machine-safe JSON output. "
    "The provider argument names the context service holding the resource, and it "
    "accepts github, slack, google-drive, or the google shorthand for Drive. "
    "The resource_type argument selects which kind of object to fetch for that provider, "
    "so github takes repo or pull-request while slack takes channel and Drive takes file. "
    "The identifier argument carries the single resource address, such as an owner and "
    "repository name, a Slack channel identifier, or a Drive file identifier or URL, and it "
    "never repeats within one invocation. Named connection selection defaults to the provider "
    "name when --connection is omitted, which is why matching connection names matter for "
    "profiles holding several accounts on the same provider."
)
_CONNECTION_OPTION_HELP = (
    "Select the saved named connection to read with for this invocation. "
    "The default is the provider name itself, which keeps single-account profiles working "
    "with no extra flag and matches the name login assigns when --name is omitted. "
    "Pass an explicit name when the profile holds several accounts on the same provider, "
    "since the command refuses to guess between them. "
    "It interacts with login --name and with profile selection, and it never accepts a "
    "provider name from a different service than the provider argument."
)
_NUMBER_OPTION_HELP = (
    "Carry the pull-request number for a github pull-request read in this invocation. "
    "The default is empty because repository, channel, and file reads address their object "
    "fully through the identifier argument and need no second coordinate. "
    "Pass a positive number exactly when resource_type is pull-request, since the read "
    "cannot address a pull request from owner and repository alone. "
    "It interacts only with the pull-request resource type and is rejected for every "
    "other type, so it costs nothing to leave unset elsewhere."
)
_LIMIT_OPTION_HELP = (
    "Bound how many Slack channel messages one read returns for this invocation. "
    "The default is 50 messages because a bounded first page keeps agent context small "
    "while still proving history access, and larger windows rarely help a first probe. "
    "Raise or lower it within 1 through 100 when the task needs a wider sample or a "
    "minimal existence check on a busy channel. "
    "It interacts only with slack channel reads and is ignored by github and Drive, so "
    "passing it elsewhere changes nothing about the result."
)


class ConnectionReadCommand:
    """Reads one repository, pull request, Slack channel, or Drive file."""

    def register(self, parent: click.Group) -> None:
        # Adds a closed provider/resource surface so arbitrary URLs never reach adapters.
        @parent.command(name="read", help=_READ_COMMAND_HELP)
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
            help=_CONNECTION_OPTION_HELP,
        )
        @click.option(
            "--number",
            type=click.IntRange(min=1),
            default=None,
            help=_NUMBER_OPTION_HELP,
        )
        @click.option(
            "--limit",
            type=click.IntRange(min=1, max=100),
            default=50,
            show_default=True,
            help=_LIMIT_OPTION_HELP,
        )
        @click.option(
            "--via",
            type=click.Choice(ReadVia.cli_choices()),
            default=ReadVia.AUTO.value,
            show_default=True,
            help=(
                "Read transport to use for this resource. The auto value prefers "
                "the provider native CLI when it is installed and authenticated, "
                "and falls back to the direct provider API otherwise. The native "
                "value requires the provider CLI and fails when it is missing. "
                "The direct value always uses the Vidbyte-authenticated API."
            ),
        )
        @click.option(
            "--show-plan",
            is_flag=True,
            default=False,
            help=(
                "Print the resolved read plan without running it. The command "
                "resolves the exact native argv or direct API target for the "
                "selected resource and transport, then exits successfully. No "
                "keyring is unlocked, no browser opens, and no provider request "
                "or subprocess runs. Use it to preview what auto would do first."
            ),
        )
        @click.pass_obj
        def _run(context: ApplicationContext, provider: str, resource_type: str, identifier: str, connection_name: str | None, number: int | None, limit: int, via: str, show_plan: bool) -> None:  # fmt: skip  # noqa: E501
            # Click owns primitive validation; the command validates provider-specific meaning.
            self.execute(
                context,
                provider,
                resource_type,
                identifier,
                connection_name,
                number,
                limit,
                via,
                show_plan,
            )

    def execute(self, context: ApplicationContext, provider: str, resource_type: str, identifier: str, connection_name: str | None, number: int | None, limit: int, via: str = "auto", show_plan: bool = False) -> None:  # fmt: skip  # noqa: E501
        # Builds one typed resource before resolving credentials or making a request.
        typed_provider = ConnectionProvider.from_cli(provider)
        typed_via = ReadVia.from_cli(via)
        self._validate_resource_type(typed_provider, resource_type)
        self._validate_number(typed_provider, resource_type, number)
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
        if show_plan:
            self._render_plan(context, resource, typed_via)
            return
        name = connection_name or typed_provider.value
        result = context.connections().read(
            context.resolved_config().profile,
            typed_provider,
            name,
            resource,
            typed_via,
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

    def _validate_number(
        self, provider: ConnectionProvider, resource_type: str, number: int | None
    ) -> None:
        # Requires a pull-request number exactly when the resource type needs one.
        if (
            provider is ConnectionProvider.GITHUB
            and resource_type == "pull-request"
            and number is None
        ):
            raise ConnectionProtocolError(
                provider.value, ValueError("pull request number is required")
            )
        if resource_type != "pull-request" and number is not None:
            raise ConnectionProtocolError(
                provider.value, ValueError("number applies only to pull-request")
            )

    def _render_plan(
        self, context: ApplicationContext, resource: ConnectionResource, via: ReadVia
    ) -> None:
        # Emits the resolved argv or API target without spawning or network access.
        plan = context.connections().plan_read(resource, via)
        data = {
            "provider": resource.provider.value,
            "resource_type": resource.resource_type,
            "identifier": resource.identifier,
            "via": via.value,
            "plan": list(plan),
        }
        human = " ".join(plan)
        context.output().result(
            OutputDocument(kind="connections.read-plan", data=cast(dict[str, JsonValue], data)),
            human,
        )

    def _render(self, context: ApplicationContext, result: ConnectionRead) -> None:
        # Emits provider data in a stable envelope and a readable terminal representation.
        data = cast(dict[str, JsonValue], result.model_dump(mode="json"))
        human = json.dumps(result.data, indent=2, sort_keys=True, ensure_ascii=False)
        context.output().result(OutputDocument(kind="connections.read", data=data), human)
        context.output().diagnostic(self._hint(result))

    def _hint(self, result: ConnectionRead) -> str:
        # Names the transport used and the deeper native command for follow-up work.
        if result.provenance.source == "gh":
            return f"Provenance: gh. Deeper: {' '.join(result.provenance.plan)}."
        if result.provider is ConnectionProvider.GITHUB and result.resource_type == "pull-request":
            return "Provenance: direct. Deeper: gh pr view <number> --repo <owner/repo> --comments."
        if result.provider is ConnectionProvider.GITHUB:
            return "Provenance: direct. Deeper: gh repo view <owner/repo> --json nameWithOwner,url."
        return "Provenance: direct."
