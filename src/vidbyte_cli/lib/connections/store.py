"""Keyring-only OAuth secrets and atomic connection metadata.

OAuth tokens never use the existing plaintext provider fallback. Metadata is kept separately so
list output can remain offline and secret-free without unlocking the keyring.
"""

from __future__ import annotations

import json
from typing import Protocol, cast

import keyring
from keyring.errors import KeyringError
from pydantic import ValidationError

from ...types.connection import (
    ConnectionDocument,
    ConnectionMetadata,
    ConnectionProvider,
    ConnectionToken,
)
from ..config.atomic import AtomicFileWriter
from ..config.paths import VidbytePaths
from ..errors.failures import (
    ConnectionNotFound,
    ConnectionStoreUnavailable,
    StoredConnectionMetadataUnreadable,
    StoredConnectionSecretUnreadable,
)

_CONNECTION_SERVICE = "vidbyte-cli-connections"
_MINIMUM_BACKEND_PRIORITY = 1
_MAX_KEYRING_VALUE = 64_000
_MAX_METADATA_BYTES = 1_000_000


class ConnectionKeyringBackend(Protocol):
    """Minimal keyring backend required by the connection secret store."""

    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class ConnectionAccount:
    """Derives one stable profile/provider/name keyring account."""

    def __init__(self, profile: str, provider: ConnectionProvider, name: str) -> None:
        # All values have already passed their public validators before reaching storage.
        self.profile = profile
        self.provider = provider
        self.name = name

    @property
    def value(self) -> str:
        # The separators keep provider and name boundaries visible during keyring inspection.
        return f"{self.profile}@{self.provider.value}@{self.name}"


class ConnectionKeyringStore:
    """Reads and writes token envelopes in the operating-system keyring."""

    def __init__(self, backend: ConnectionKeyringBackend | None = None) -> None:
        # Backend injection keeps tests away from the developer's real keyring.
        self._backend = backend

    def available(self) -> bool:
        # Availability is a branch condition, not itself a user-facing failure.
        try:
            return float(self._get_backend().priority) >= _MINIMUM_BACKEND_PRIORITY
        except (KeyringError, RuntimeError, TypeError, ValueError):
            return False

    def read(self, profile: str, provider: ConnectionProvider, name: str) -> ConnectionToken | None:
        # Reads one profile/provider/name token and validates the complete envelope.
        if not self.available():
            raise ConnectionStoreUnavailable()
        try:
            raw = self._get_backend().get_password(
                _CONNECTION_SERVICE,
                ConnectionAccount(profile, provider, name).value,
            )
        except (KeyringError, RuntimeError, OSError) as error:
            raise ConnectionStoreUnavailable(error) from error
        if raw is None:
            return None
        try:
            if len(raw.encode("utf-8")) > _MAX_KEYRING_VALUE:
                raise ValueError("connection token envelope is oversized")
            return ConnectionToken.model_validate_json(raw)
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            raise StoredConnectionSecretUnreadable(error) from error

    def write(self, profile: str, provider: ConnectionProvider, name: str, token: ConnectionToken) -> None:  # fmt: skip  # noqa: E501
        # Writes and reads back one complete token envelope before reporting success.
        if not self.available():
            raise ConnectionStoreUnavailable()
        account = ConnectionAccount(profile, provider, name).value
        raw = self._encode(token)
        try:
            backend = self._get_backend()
            backend.set_password(_CONNECTION_SERVICE, account, raw)
            read_back = backend.get_password(_CONNECTION_SERVICE, account)
        except (KeyringError, RuntimeError, OSError) as error:
            raise ConnectionStoreUnavailable(error) from error
        if read_back != raw:
            raise ConnectionStoreUnavailable()

    def clear(self, profile: str, provider: ConnectionProvider, name: str) -> bool:
        # Removes one keyring entry and verifies that it no longer reads back.
        if not self.available():
            raise ConnectionStoreUnavailable()
        account = ConnectionAccount(profile, provider, name).value
        try:
            backend = self._get_backend()
            if backend.get_password(_CONNECTION_SERVICE, account) is None:
                return False
            backend.delete_password(_CONNECTION_SERVICE, account)
            if backend.get_password(_CONNECTION_SERVICE, account) is not None:
                raise RuntimeError("connection keyring entry remained after delete")
            return True
        except (KeyringError, RuntimeError, OSError) as error:
            raise ConnectionStoreUnavailable(error) from error

    def _get_backend(self) -> ConnectionKeyringBackend:
        # Lazy discovery avoids keychain prompts while Click builds --help.
        if self._backend is None:
            self._backend = cast(ConnectionKeyringBackend, keyring.get_keyring())
        return self._backend

    def _encode(self, token: ConnectionToken) -> str:
        # These are the only deliberate unwraps of OAuth bearer credentials.
        payload = {
            "schema_version": token.schema_version,
            "access_token": token.access_secret(),
            "refresh_token": token.refresh_secret(),
            "token_type": token.token_type,
            "expires_at": token.expires_at,
            "provider_data": token.provider_data,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        if len(raw.encode("utf-8")) > _MAX_KEYRING_VALUE:
            raise ConnectionStoreUnavailable()
        return raw


class ConnectionMetadataStore:
    """Reads and atomically writes secret-free connection metadata."""

    def __init__(self, paths: VidbytePaths, writer: AtomicFileWriter | None = None) -> None:
        # Paths and writer injection make metadata tests isolated and deterministic.
        self._paths = paths
        self._writer = writer or AtomicFileWriter()

    def list(self, profile: str) -> list[ConnectionMetadata]:
        # Returns only the selected profile in stable provider/name order.
        entries = [entry for entry in self._load().entries if entry.profile == profile]
        return sorted(entries, key=lambda item: (item.provider.value, item.name))

    def read(self, profile: str, provider: ConnectionProvider, name: str) -> ConnectionMetadata | None:  # fmt: skip  # noqa: E501
        # Looks up metadata without touching the keyring or network.
        for entry in self._load().entries:
            if entry.profile == profile and entry.provider is provider and entry.name == name:
                return entry
        return None

    def write(self, profile: str, metadata: ConnectionMetadata) -> None:
        # Replaces the matching profile/provider/name entry through an atomic whole-document write.
        entries = [
            entry
            for entry in self._load().entries
            if not (
                entry.profile == profile
                and entry.provider is metadata.provider
                and entry.name == metadata.name
            )
        ]
        entries.append(metadata)
        document = ConnectionDocument(entries=tuple(entries))
        self._writer.write(self._paths.connection_metadata_file(), self._encode(document))

    def clear(self, profile: str, provider: ConnectionProvider, name: str) -> bool:
        # Removes metadata for one connection and leaves an empty versioned document if needed.
        document = self._load()
        remaining = tuple(
            entry
            for entry in document.entries
            if not (entry.profile == profile and entry.provider is provider and entry.name == name)
        )
        if len(remaining) == len(document.entries):
            return False
        self._writer.write(
            self._paths.connection_metadata_file(),
            self._encode(ConnectionDocument(entries=remaining)),
        )
        return True

    def _load(self) -> ConnectionDocument:
        # Bounds bytes before parsing so a damaged file cannot consume unbounded memory.
        path = self._paths.connection_metadata_file()
        if not path.exists():
            return ConnectionDocument()
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_METADATA_BYTES:
                raise ValueError("connection metadata is oversized")
            return ConnectionDocument.model_validate_json(raw)
        except (OSError, ValueError, ValidationError) as error:
            raise StoredConnectionMetadataUnreadable(error) from error

    def _encode(self, document: ConnectionDocument) -> bytes:
        # Pydantic serializes only the secret-free metadata model.
        return document.model_dump_json(indent=2).encode("utf-8") + b"\n"


class ConnectionStore:
    """Coordinates keyring tokens and metadata as one recoverable local mutation."""

    def __init__(self, paths: VidbytePaths, keyring_store: ConnectionKeyringStore | None = None) -> None:  # fmt: skip  # noqa: E501
        # The manager supplies the invocation's platform paths and tests can inject a backend.
        self.keyring = keyring_store or ConnectionKeyringStore()
        self.metadata = ConnectionMetadataStore(paths)

    def save(self, profile: str, token: ConnectionToken, metadata: ConnectionMetadata) -> None:
        # Replaces a named connection only after the new token and metadata are both durable.
        previous = self.keyring.read(profile, metadata.provider, metadata.name)
        self.keyring.write(profile, metadata.provider, metadata.name, token)
        try:
            self.metadata.write(profile, metadata)
        except Exception:
            # Restore the prior bearer envelope if the metadata half cannot be committed.
            if previous is None:
                self.keyring.clear(profile, metadata.provider, metadata.name)
            else:
                self.keyring.write(profile, metadata.provider, metadata.name, previous)
            raise

    def load(self, profile: str, provider: ConnectionProvider, name: str) -> tuple[ConnectionToken, ConnectionMetadata]:  # fmt: skip  # noqa: E501
        # Requires both halves so a dangling metadata or secret entry cannot look authenticated.
        metadata = self.metadata.read(profile, provider, name)
        if metadata is None:
            raise ConnectionNotFound()
        token = self.keyring.read(profile, provider, name)
        if token is None:
            raise ConnectionNotFound()
        return token, metadata

    def remove(self, profile: str, provider: ConnectionProvider, name: str) -> None:
        # Clears the token and metadata for one named connection.
        self.keyring.clear(profile, provider, name)
        self.metadata.clear(profile, provider, name)
