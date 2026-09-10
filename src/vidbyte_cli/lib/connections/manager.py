"""Lifecycle service for named context-provider connections.

The manager is the only layer that combines command-selected names, provider adapters, keyring
tokens, and secret-free metadata.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from ...types.connection import (
    ConnectionIdentity,
    ConnectionMetadata,
    ConnectionProvider,
    ConnectionRead,
    ConnectionResource,
    ConnectionToken,
)
from ..errors.cli_error import CliError
from ..errors.failures import (
    ConnectionNotFound,
    ConnectionProtocolError,
    ConnectionReauthenticationRequired,
)
from .providers.base import AuthenticatedConnection, ConnectionProviderAdapter
from .providers.github import GitHubConnectionAdapter
from .providers.google_drive import GoogleDriveConnectionAdapter
from .providers.slack import SlackConnectionAdapter
from .store import ConnectionStore

if TYPE_CHECKING:
    from ..runtime.context import ApplicationContext

_REFRESH_SAFETY_SECONDS = 300


class ConnectionManager:
    """Runs provider-independent connection lifecycle operations."""

    def __init__(self, context: ApplicationContext) -> None:
        # The manager receives the invocation graph but does not construct it eagerly.
        self._context = context
        self._store = ConnectionStore(context.paths())
        self._adapters: dict[ConnectionProvider, ConnectionProviderAdapter] = {
            ConnectionProvider.GITHUB: GitHubConnectionAdapter(),
            ConnectionProvider.SLACK: SlackConnectionAdapter(),
            ConnectionProvider.GOOGLE_DRIVE: GoogleDriveConnectionAdapter(),
        }

    def login(self, provider: ConnectionProvider, name: str, scopes: tuple[str, ...], client_secrets_path: Path | None = None) -> ConnectionMetadata:  # fmt: skip  # noqa: E501
        # Verifies a new provider identity before replacing any named connection.
        self._validate_name(name)
        authenticated = self._adapter(provider).login(self._context, scopes, client_secrets_path)
        profile = self._profile()
        metadata = self._metadata(profile, provider, name, authenticated)
        self._store.save(profile, authenticated.token, metadata)
        return metadata

    def list(self, profile: str) -> list[ConnectionMetadata]:
        # Lists secret-free metadata without unlocking the keyring or making a network request.
        return self._store.metadata.list(profile)

    def status(self, profile: str, provider: ConnectionProvider, name: str) -> ConnectionMetadata:
        # Refreshes if needed, verifies identity, and returns current non-secret metadata.
        token, metadata = self._resolve(profile, provider, name)
        identity = self._adapter(provider).verify(self._context, token)
        self._ensure_identity(metadata, identity)
        return self._metadata_from_identity(metadata, token, identity)

    def status_by_name(self, profile: str, name: str) -> ConnectionMetadata:
        # Resolves a unique name so the concise status command remains provider-agnostic.
        metadata = self._find_unique(profile, name)
        return self.status(profile, metadata.provider, metadata.name)

    def read(self, profile: str, provider: ConnectionProvider, name: str, resource: ConnectionResource) -> ConnectionRead:  # fmt: skip  # noqa: E501
        # Resolves a current token and dispatches one bounded resource read.
        token, _ = self._resolve(profile, provider, name)
        self._ensure_resource(resource, provider)
        return self._adapter(provider).read(self._context, token, resource)

    def logout(self, profile: str, provider: ConnectionProvider, name: str) -> None:
        # Attempts provider revocation but always clears the local connection afterward.
        token, _ = self._store.load(profile, provider, name)
        revoke_error: CliError | None = None
        try:
            self._adapter(provider).revoke(self._context, token)
        except CliError as error:
            revoke_error = error
        self._store.remove(profile, provider, name)
        if revoke_error is not None:
            self._context.output().warning(
                "The local connection was removed, but provider-side revocation "
                "could not be confirmed."
            )

    def logout_by_name(self, profile: str, name: str) -> None:
        # Resolves one unique name before applying the provider-specific logout behavior.
        metadata = self._find_unique(profile, name)
        self.logout(profile, metadata.provider, metadata.name)

    def _resolve(self, profile: str, provider: ConnectionProvider, name: str) -> tuple[ConnectionToken, ConnectionMetadata]:  # fmt: skip  # noqa: E501
        # Loads a pair and atomically persists any verified refresh replacement.
        token, metadata = self._store.load(profile, provider, name)
        refresh_deadline = int(time.time()) + _REFRESH_SAFETY_SECONDS
        if token.expires_at is None or token.expires_at > refresh_deadline:
            return token, metadata
        if token.refresh_secret() is None:
            raise ConnectionReauthenticationRequired(provider.value)
        refreshed = self._adapter(provider).refresh(self._context, token)
        identity = self._adapter(provider).verify(self._context, refreshed)
        self._ensure_identity(metadata, identity)
        updated = self._metadata_from_identity(metadata, refreshed, identity)
        self._store.save(profile, refreshed, updated)
        return refreshed, updated

    def _metadata(self, profile: str, provider: ConnectionProvider, name: str, authenticated: AuthenticatedConnection) -> ConnectionMetadata:  # fmt: skip  # noqa: E501
        # Converts verified identity and token state into secret-free metadata.
        identity = authenticated.identity
        try:
            return ConnectionMetadata(
                profile=profile,
                provider=provider,
                name=name,
                account_id=identity.account_id,
                account_label=identity.account_label,
                workspace_id=identity.workspace_id,
                workspace_label=identity.workspace_label,
                scopes=identity.scopes,
                token_type=authenticated.token.token_type,
                expires_at=authenticated.token.expires_at,
            )
        except ValidationError as error:
            raise ConnectionProtocolError(provider.value, error) from error

    def _metadata_from_identity(self, previous: ConnectionMetadata, token: ConnectionToken, identity: ConnectionIdentity) -> ConnectionMetadata:  # fmt: skip  # noqa: E501
        # Retains the named connection while updating provider-owned identity metadata.
        try:
            return ConnectionMetadata.model_validate(
                previous.model_copy(
                    update={
                        "account_id": identity.account_id,
                        "account_label": identity.account_label,
                        "workspace_id": identity.workspace_id,
                        "workspace_label": identity.workspace_label,
                        "scopes": identity.scopes or previous.scopes,
                        "token_type": token.token_type,
                        "expires_at": token.expires_at,
                    }
                )
            )
        except ValidationError as error:
            raise ConnectionProtocolError(previous.provider.value, error) from error

    def _ensure_identity(self, expected: ConnectionMetadata, actual: ConnectionIdentity) -> None:
        # Refuses a swapped keyring token that belongs to a different provider account.
        if (
            expected.account_id != actual.account_id
            or expected.workspace_id != actual.workspace_id
            or expected.provider is not actual.provider
        ):
            raise ConnectionProtocolError(
                expected.provider.value,
                ValueError("connection identity changed"),
            )

    def _ensure_resource(self, resource: ConnectionResource, provider: ConnectionProvider) -> None:
        # Rejects a resource whose provider differs from the selected named connection.
        if resource.provider is not provider:
            raise ConnectionProtocolError(provider.value, ValueError("resource provider mismatch"))

    def _adapter(self, provider: ConnectionProvider) -> ConnectionProviderAdapter:
        # Returns the statically registered provider adapter.
        adapter = self._adapters.get(provider)
        if adapter is None:
            raise ConnectionNotFound()
        return adapter

    def _find_unique(self, profile: str, name: str) -> ConnectionMetadata:
        # Finds one name and refuses an ambiguous cross-provider selection.
        matches = [entry for entry in self._store.metadata.list(profile) if entry.name == name]
        if not matches:
            raise ConnectionNotFound()
        if len(matches) != 1:
            raise ConnectionProtocolError("connection", ValueError("connection name is ambiguous"))
        return matches[0]

    def _profile(self) -> str:
        # Uses the already resolved invocation profile for the newly saved connection.
        return self._context.resolved_config().profile

    def _validate_name(self, name: str) -> None:
        # Validates the keyring identifier before opening a browser or sending a request.
        try:
            ConnectionMetadata(
                profile=self._profile(),
                provider=ConnectionProvider.GITHUB,
                name=name,
                account_id="pending",
            )
        except ValidationError as error:
            raise ConnectionProtocolError("connection", error) from error
