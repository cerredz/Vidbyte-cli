"""Which credential this invocation uses, and where it came from.

Order is environment → OS keyring → restricted file. Secrets get their own precedence
because a CI job exporting `VIDBYTE_API_KEY` must win over whatever a developer once stored
on the same machine, while non-secret config follows the profile layering in `lib/config`.

Reading is all this does. Login deliberately does not resolve through here, which is what
keeps an environment token from being written into durable storage as if it were entered.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ..errors.failures import InvalidEnvironmentApiKey
from .credentials import Credentials, CredentialStore

_MAX_KEY_CHARACTERS = 4096


class CredentialSource(StrEnum):
    """Stable non-secret provenance for a resolved credential."""

    ENVIRONMENT = "environment"
    KEYRING = "keyring"
    RESTRICTED_FILE = "restricted_file"


@dataclass(frozen=True)
class ResolvedCredential:
    """Secret-safe credential plus non-secret provenance."""

    credentials: Credentials
    source: CredentialSource


class CredentialResolver:
    """Read one scoped credential according to documented precedence."""

    def __init__(self, store: CredentialStore, environment: Mapping[str, str]) -> None:
        self._store = store
        self._environment = environment

    def resolve(self, profile: str, api_url: str) -> ResolvedCredential | None:
        environment_value = self._environment.get("VIDBYTE_API_KEY")
        if environment_value is not None:
            # Set-but-unusable is an error, not a miss: falling through would silently
            # authenticate as whoever is stored locally, which the caller did not ask for.
            token = environment_value.strip()
            if not token or len(token) > _MAX_KEY_CHARACTERS:
                raise InvalidEnvironmentApiKey()
            return ResolvedCredential(Credentials.from_value(token), CredentialSource.ENVIRONMENT)
        keyring_value = self._store.keyring.read(profile, api_url)
        if keyring_value is not None:
            return ResolvedCredential(keyring_value, CredentialSource.KEYRING)
        file_value = self._store.file.read(profile, api_url)
        if file_value is not None:
            return ResolvedCredential(file_value, CredentialSource.RESTRICTED_FILE)
        return None
