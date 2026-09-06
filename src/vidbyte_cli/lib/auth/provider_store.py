"""Keyring-first provider credential facade.

Mirrors CredentialStore but namespaces to vidbyte-cli-provider and scopes by provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

import keyring
from keyring.errors import KeyringError
from pydantic import ValidationError

from ...types.provider import Provider
from ..config.paths import VidbytePaths
from ..errors.failures import NoApprovedProviderStore, ProviderStoreUnavailable
from .provider_credentials import (
    FileProviderStore,
    ProviderCredentials,
    ProviderScope,
    ProviderStorage,
)

if TYPE_CHECKING:
    pass

_PROVIDER_SERVICE = "vidbyte-cli-provider"
_MINIMUM_BACKEND_PRIORITY = 1


class ProviderKeyringBackend(Protocol):
    """Small structural surface needed from the provider keyring backend."""

    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class KeyringProviderStore:
    """Secret store for provider keys backed by the OS keyring."""

    def __init__(self, backend: ProviderKeyringBackend | None = None) -> None:
        # Backend injectable for tests; otherwise resolved lazily.
        self._backend = backend

    def available(self) -> bool:
        # Availability is a question, not a failure.
        try:
            return float(self._get_backend().priority) >= _MINIMUM_BACKEND_PRIORITY
        except (KeyringError, RuntimeError, TypeError, ValueError):
            return False

    def read(self, profile: str, provider: Provider) -> ProviderCredentials | None:
        # Returns None when unavailable or missing; raises only on backend errors.
        if not self.available():
            return None
        try:
            value = self._get_backend().get_password(
                _PROVIDER_SERVICE,
                ProviderScope(profile, provider).account,
            )
        except KeyringError as error:
            raise ProviderStoreUnavailable(error) from error
        if value is None:
            return None
        try:
            return ProviderCredentials(provider=provider, api_key=value)  # type: ignore[arg-type]
        except ValidationError as error:
            raise ProviderStoreUnavailable(error) from error

    def write(self, credentials: ProviderCredentials, profile: str, provider: Provider) -> None:
        # Verifies write by reading back; a lying backend must not report success.
        if not self.available():
            raise ProviderStoreUnavailable()
        account = ProviderScope(profile, provider).account
        try:
            backend = self._get_backend()
            backend.set_password(_PROVIDER_SERVICE, account, credentials.secret_value())
            read_back = backend.get_password(_PROVIDER_SERVICE, account)
        except KeyringError as error:
            raise ProviderStoreUnavailable(error) from error
        if read_back != credentials.secret_value():
            raise ProviderStoreUnavailable()

    def clear(self, profile: str, provider: Provider) -> bool:
        # Clears the keyring entry if present.
        if not self.available():
            return False
        account = ProviderScope(profile, provider).account
        try:
            backend = self._get_backend()
            if backend.get_password(_PROVIDER_SERVICE, account) is None:
                return False
            backend.delete_password(_PROVIDER_SERVICE, account)
            return True
        except KeyringError as error:
            raise ProviderStoreUnavailable(error) from error

    def _get_backend(self) -> ProviderKeyringBackend:
        # Resolved on first use and cached; discovery can open a keychain session.
        if self._backend is None:
            self._backend = cast(ProviderKeyringBackend, keyring.get_keyring())
        return self._backend


class ProviderCredentialStore:
    """Keyring-first durable provider credential facade."""

    def __init__(
        self,
        keyring_store: KeyringProviderStore | None = None,
        file_store: FileProviderStore | None = None,
        paths: VidbytePaths | None = None,
    ) -> None:
        # Composition mirrors CredentialStore for test injection.
        resolved_paths = paths or VidbytePaths.default()
        self.keyring = keyring_store or KeyringProviderStore()
        self.file = file_store or FileProviderStore(resolved_paths)

    def read(self, profile: str, provider: Provider) -> ProviderCredentials | None:
        # Keyring outranks file; file is fallback.
        return self.keyring.read(profile, provider) or self.file.read(profile, provider)

    def write(
        self,
        credentials: ProviderCredentials,
        profile: str,
        provider: Provider,
        *,
        allow_file_fallback: bool = False,
    ) -> ProviderStorage:
        # Writes to keyring when available; otherwise file with consent.
        if self.keyring.available():
            self.keyring.write(credentials, profile, provider)
            return ProviderStorage.KEYRING
        if not allow_file_fallback:
            raise NoApprovedProviderStore(provider.value)
        self.file.write(credentials, profile, provider)
        return ProviderStorage.RESTRICTED_FILE

    def clear(self, profile: str, provider: Provider) -> bool:
        # Clears both stores; a stale entry in either would stay effective.
        keyring_cleared = self.keyring.clear(profile, provider)
        file_cleared = self.file.clear(profile, provider)
        return keyring_cleared or file_cleared
