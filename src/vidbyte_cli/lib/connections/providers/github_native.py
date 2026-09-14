"""GitHub reads served from the provider-owned gh CLI.

Builds only two allowlisted argv shapes and normalizes gh --json into the
shared ConnectionRead contract with gh provenance. No Vidbyte token is used.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter, ValidationError

from ....types.connection import (
    ConnectionProvider,
    ConnectionRead,
    ConnectionResource,
    ReadProvenance,
)
from ...errors.failures import ConnectionProtocolError, ConnectionResourceUnavailable

if TYPE_CHECKING:
    from ...runtime.context import ApplicationContext
    from ..native import NativeAvailability, NativeProbe

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_REPO_FIELDS = "nameWithOwner,description,url,primaryLanguage,stargazerCount"
_PR_FIELDS = "number,title,body,state,url,comments"


class GitHubNativeAdapter:
    """Reads GitHub repos and pull requests through allowlisted gh commands."""

    provider = ConnectionProvider.GITHUB

    def __init__(self, probe: NativeProbe | None = None) -> None:
        # Probe injection keeps tests offline with a fake gh on PATH.
        from ..native import NativeProbe as ProbeType

        self._probe: NativeProbe = probe if probe is not None else ProbeType()

    def supports(self, resource: ConnectionResource) -> bool:
        # Only GitHub repo and pull-request resources can use the native path.
        return resource.provider is ConnectionProvider.GITHUB and resource.resource_type in {
            "repo",
            "pull-request",
        }

    def plan(self, resource: ConnectionResource) -> tuple[str, ...]:
        # Returns the exact argv that would run, without spawning anything.
        self._require_supported(resource)
        owner, repository = self._repository_parts(resource.identifier)
        if resource.resource_type == "repo":
            return ("gh", "repo", "view", f"{owner}/{repository}", "--json", _REPO_FIELDS)
        return (
            "gh",
            "pr",
            "view",
            str(resource.number),
            "--repo",
            f"{owner}/{repository}",
            "--json",
            _PR_FIELDS,
        )

    def availability(self) -> NativeAvailability:
        # Exposes the cached probe so status can report without spawning twice.
        return self._probe.github()

    def read(self, context: ApplicationContext, resource: ConnectionResource) -> ConnectionRead:
        # Validates, probes, runs gh, and normalizes --json into ConnectionRead.
        from ...errors.failures import ConnectionAuthenticationRequired
        from ..native import NativeRunner

        self._require_supported(resource)
        available = self._probe.github()
        if not available.found:
            from ...errors.failures import ConnectionNativeCliMissing

            raise ConnectionNativeCliMissing("gh")
        if not available.authenticated:
            raise ConnectionAuthenticationRequired("github")
        argv = self.plan(resource)
        payload = NativeRunner(context.options.request_timeout_seconds).run(argv).payload
        return self._to_read(resource, argv, payload)

    def _require_supported(self, resource: ConnectionResource) -> None:
        # Rejects wrong-provider or wrong-type resources before any probe or spawn.
        if not self.supports(resource):
            raise ConnectionProtocolError("github", ValueError("resource type is unsupported"))
        if resource.resource_type == "pull-request" and resource.number is None:
            raise ConnectionResourceUnavailable("github")

    def _repository_parts(self, identifier: str) -> tuple[str, str]:
        # Validates owner/repo before either value reaches native argv.
        if not _REPO_PATTERN.fullmatch(identifier):
            raise ConnectionProtocolError("github", ValueError("repository must be owner/name"))
        owner, repository = identifier.split("/")
        return (owner, repository)

    def _to_read(
        self, resource: ConnectionResource, argv: tuple[str, ...], payload: dict[str, object]
    ) -> ConnectionRead:
        # Normalizes gh --json and stamps gh provenance on every success.
        try:
            data = TypeAdapter(dict[str, JsonValue]).validate_python(payload)
        except ValidationError as error:
            raise ConnectionProtocolError("github", error) from error
        if resource.resource_type == "repo" and not data.get("nameWithOwner"):
            raise ConnectionProtocolError("github", ValueError("native repo shape"))
        if resource.resource_type == "pull-request" and "number" not in data:
            raise ConnectionProtocolError("github", ValueError("native pull-request shape"))
        try:
            return ConnectionRead(
                provider=self.provider,
                resource_type=resource.resource_type,
                identifier=resource.identifier,
                data=data,
                provenance=ReadProvenance(source="gh", plan=argv),
            )
        except ValidationError as error:
            raise ConnectionProtocolError("github", error) from error
