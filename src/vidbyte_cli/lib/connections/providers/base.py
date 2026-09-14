"""Shared provider adapter contracts and safe response helpers.

Provider adapters own external protocol details while the connection manager owns lifecycle,
storage, and provider-independent command behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import JsonValue, TypeAdapter, ValidationError

from ....types.connection import (
    ConnectionIdentity,
    ConnectionProvider,
    ConnectionRead,
    ConnectionResource,
    ConnectionToken,
)
from ...errors.failures import ConnectionProtocolError
from ..oauth import OAuthHttpClient

if TYPE_CHECKING:
    from ...runtime.context import ApplicationContext


@dataclass(frozen=True)
class AuthenticatedConnection:
    """The verified result of a provider login."""

    token: ConnectionToken
    identity: ConnectionIdentity


class ProviderAdapterBase:
    """Reusable safe parsing and authenticated-client helpers."""

    def _client(self, context: ApplicationContext, provider: str) -> OAuthHttpClient:
        # Every provider request shares the invocation timeout and non-redirecting client.
        return OAuthHttpClient(provider, context.options.request_timeout_seconds)

    def _headers(self, token: ConnectionToken) -> dict[str, str]:
        # Bearer values are unwrapped only at the outgoing HTTP boundary.
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token.access_secret()}",
        }

    def _text(self, payload: dict[str, object], key: str, provider: str) -> str:
        # Required provider strings are validated without reflecting their values on failure.
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ConnectionProtocolError(provider, ValueError(f"missing {key}"))
        return value

    def _optional_text(self, payload: dict[str, object], key: str) -> str | None:
        # Optional provider strings remain absent when the API omits them.
        value = payload.get(key)
        return value if isinstance(value, str) and value else None

    def _integer(self, payload: dict[str, object], key: str, provider: str) -> int:
        # Required duration and identity fields reject booleans and fractional values.
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConnectionProtocolError(provider, ValueError(f"invalid {key}"))
        return value

    def _optional_integer(self, payload: dict[str, object], key: str) -> int | None:
        # Optional expiry values stay unset when a provider issues a non-expiring token.
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    def _scopes(self, value: object) -> tuple[str, ...]:
        # Provider scope strings use commas or whitespace and are normalized only for metadata.
        if not isinstance(value, str):
            return ()
        return tuple(
            dict.fromkeys(part.strip() for part in value.replace(",", " ").split() if part.strip())
        )

    def _json_data(self, payload: dict[str, object], provider: str) -> dict[str, JsonValue]:
        # Validates arbitrary provider JSON before it crosses into the output contract.
        try:
            return TypeAdapter(dict[str, JsonValue]).validate_python(payload)
        except ValidationError as error:
            raise ConnectionProtocolError(provider, error) from error

    def _resource_for(self, resource: ConnectionResource, provider: ConnectionProvider) -> None:
        # Prevents a provider adapter from accidentally reading another provider's resource.
        if resource.provider is not provider:
            raise ConnectionProtocolError(provider.value, ValueError("resource provider mismatch"))

    def _path_component(self, value: str, provider: str) -> str:
        # URL path components accept only conservative provider identifiers.
        import re

        if not re.fullmatch(r"[A-Za-z0-9._~-]+", value):
            raise ConnectionProtocolError(provider, ValueError("unsafe path component"))
        return value


class ConnectionProviderAdapter(Protocol):
    """Provider-specific OAuth, identity, refresh, revoke, and read surface."""

    provider: ConnectionProvider

    def login(self, context: ApplicationContext, scopes: tuple[str, ...], client_secrets_path: Path | None = None) -> AuthenticatedConnection:  # fmt: skip  # noqa: E501
        # Runs the provider's interactive login and verifies the resulting identity.
        ...

    def verify(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionIdentity:
        # Proves that a stored token still identifies the expected provider account.
        ...

    def refresh(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionToken:
        # Exchanges a provider refresh token for a new access token.
        ...

    def read(self, context: ApplicationContext, token: ConnectionToken, resource: ConnectionResource) -> ConnectionRead:  # fmt: skip  # noqa: E501
        # Reads one bounded resource using the selected connection.
        ...

    def revoke(self, context: ApplicationContext, token: ConnectionToken) -> None:
        # Attempts provider-side revocation without affecting local removal.
        ...
