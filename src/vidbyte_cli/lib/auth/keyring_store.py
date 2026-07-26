"""FILE: src/vidbyte_cli/lib/auth/keyring_store.py

PURPOSE: Adapts the system keyring backend to profile/API-host-scoped Vidbyte credentials
and translates backend failures without exposing secret values or provider internals.

ROLE IN CODEBASE: CredentialStore prefers this adapter; StateMigration writes legacy
credentials here only when the backend is viable and read-back succeeds.

ARCHITECTURE NOTE: The keyring service is `vidbyte-cli`; account identity is
`<profile>@<normalized-host>`. A backend priority below one is treated as unavailable.

FUNCTION INVENTORY (reviewed 2026-07-26):
- credential_account(profile, api_url) -> str: creates stable secret scope.
- KeyringCredentialStore.available() -> bool: checks backend viability.
- read(), write(), clear(): perform safe scoped keyring operations.

WHAT NOT TO DO IN THIS FILE:
1. Do not use one global account across profiles or API hosts.
2. Do not include backend exception text or tokens in CliError messages.
3. Do not claim a write succeeded before reading the same token back.
4. Do not import or initialize keyring at module-global construction time.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlsplit

import keyring
from keyring.errors import KeyringError
from pydantic import ValidationError

from ..config.models import ProfileConfig
from ..errors import CliError, CliErrorCode

if TYPE_CHECKING:
    from .credentials import Credentials

_SERVICE_NAME = "vidbyte-cli"


class KeyringBackend(Protocol):
    """Small structural surface needed from an installed keyring backend."""

    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def credential_account(profile: str, api_url: str) -> str:
    normalized = ProfileConfig(api_url=api_url).api_url
    parsed = urlsplit(normalized)
    host = parsed.hostname or ""
    default_port = parsed.port is None or (parsed.scheme, parsed.port) in {
        ("https", 443),
        ("http", 80),
    }
    host_scope = host if default_port else f"{host}:{parsed.port}"
    return f"{profile}@{host_scope.lower()}"


class KeyringCredentialStore:
    """Secret store backed by the active system keyring."""

    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend = backend

    def available(self) -> bool:
        try:
            backend = self._get_backend()
            return float(backend.priority) >= 1
        except (KeyringError, RuntimeError, TypeError, ValueError):
            return False

    def read(self, profile: str, api_url: str) -> Credentials | None:
        if not self.available():
            return None
        try:
            value = self._get_backend().get_password(
                _SERVICE_NAME,
                credential_account(profile, api_url),
            )
        except KeyringError as error:
            raise self._failure(error) from error
        if value is None:
            return None
        from .credentials import Credentials

        try:
            return Credentials.from_value(value)
        except ValidationError as error:
            raise self._failure(error) from error

    def write(self, credentials: Credentials, profile: str, api_url: str) -> None:
        if not self.available():
            raise self._failure()
        account = credential_account(profile, api_url)
        try:
            backend = self._get_backend()
            backend.set_password(_SERVICE_NAME, account, credentials.secret_value())
            read_back = backend.get_password(_SERVICE_NAME, account)
        except KeyringError as error:
            raise self._failure(error) from error
        if read_back != credentials.secret_value():
            raise self._failure()

    def clear(self, profile: str, api_url: str) -> bool:
        if not self.available():
            return False
        account = credential_account(profile, api_url)
        try:
            backend = self._get_backend()
            if backend.get_password(_SERVICE_NAME, account) is None:
                return False
            backend.delete_password(_SERVICE_NAME, account)
            return True
        except KeyringError as error:
            raise self._failure(error) from error

    def _get_backend(self) -> KeyringBackend:
        if self._backend is None:
            self._backend = cast(KeyringBackend, keyring.get_keyring())
        return self._backend

    def _failure(self, cause: Exception | None = None) -> CliError:
        return CliError(
            CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
            "The operating-system credential store is unavailable.",
            hint="Check the system keyring, or explicitly approve the restricted-file fallback.",
            cause=cause,
        )
