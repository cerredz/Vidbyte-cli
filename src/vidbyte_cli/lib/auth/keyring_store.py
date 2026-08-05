"""The system keyring, adapted to profile- and API-origin-scoped Vidbyte credentials.

Every stored secret is scoped, so one profile cannot read another's key and a staging login
cannot authenticate against production. A backend failure is translated, never propagated:
keyring exceptions routinely quote account identifiers and backend internals.

A write is not believed until the same value reads back. Some backends accept a write and
store nothing, and a login that reports success while storing nothing is worse than failing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

import keyring
from keyring.errors import KeyringError
from pydantic import ValidationError

from ..config.models import ApiOrigin
from ..errors.failures import CredentialStoreUnavailable

if TYPE_CHECKING:
    from .credentials import Credentials

_SERVICE_NAME = "vidbyte-cli"
# keyring's own null and fail backends sit below 1; anything at or above it is a real store.
_MINIMUM_BACKEND_PRIORITY = 1


class KeyringBackend(Protocol):
    """Small structural surface needed from an installed keyring backend."""

    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class CredentialScope:
    """The profile and API origin that one stored secret belongs to."""

    def __init__(self, profile: str, api_url: str) -> None:
        self.profile = profile
        self.origin = ApiOrigin.parse(api_url)

    @property
    def account(self) -> str:
        # The default port is omitted so `https://api.vidbyte.ai` and `https://api.vidbyte.ai:443`
        # resolve to one entry rather than two credentials that silently disagree.
        port = self.origin.port
        scheme = self.origin.scheme
        is_default_port = port is None or (scheme, port) in {("https", 443), ("http", 80)}
        host = self.origin.host if is_default_port else f"{self.origin.host}:{port}"
        return f"{self.profile}@{host}"


class KeyringCredentialStore:
    """Secret store backed by the active system keyring."""

    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend = backend

    def available(self) -> bool:
        # Availability is a question, not a failure: callers branch on it to choose the
        # fallback path, so a broken backend answers False instead of raising.
        try:
            return float(self._get_backend().priority) >= _MINIMUM_BACKEND_PRIORITY
        except (KeyringError, RuntimeError, TypeError, ValueError):
            return False

    def read(self, profile: str, api_url: str) -> Credentials | None:
        if not self.available():
            return None
        try:
            value = self._get_backend().get_password(
                _SERVICE_NAME,
                CredentialScope(profile, api_url).account,
            )
        except KeyringError as error:
            raise CredentialStoreUnavailable(error) from error
        if value is None:
            return None
        # Deferred: importing at module scope would cycle, since credentials.py needs this
        # module's scope type to address its own entries.
        from .credentials import Credentials

        try:
            return Credentials.from_value(value)
        except ValidationError as error:
            raise CredentialStoreUnavailable(error) from error

    def write(self, credentials: Credentials, profile: str, api_url: str) -> None:
        if not self.available():
            raise CredentialStoreUnavailable()
        account = CredentialScope(profile, api_url).account
        try:
            backend = self._get_backend()
            backend.set_password(_SERVICE_NAME, account, credentials.secret_value())
            read_back = backend.get_password(_SERVICE_NAME, account)
        except KeyringError as error:
            raise CredentialStoreUnavailable(error) from error
        if read_back != credentials.secret_value():
            raise CredentialStoreUnavailable()

    def clear(self, profile: str, api_url: str) -> bool:
        if not self.available():
            return False
        account = CredentialScope(profile, api_url).account
        try:
            backend = self._get_backend()
            if backend.get_password(_SERVICE_NAME, account) is None:
                return False
            backend.delete_password(_SERVICE_NAME, account)
            return True
        except KeyringError as error:
            raise CredentialStoreUnavailable(error) from error

    def _get_backend(self) -> KeyringBackend:
        # Resolved on first use and cached: backend discovery can open a keychain session,
        # which must not happen while the command tree is being built.
        if self._backend is None:
            self._backend = cast(KeyringBackend, keyring.get_keyring())
        return self._backend
