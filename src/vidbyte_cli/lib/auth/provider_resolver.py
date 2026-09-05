"""Which provider credential this invocation uses and where it came from.

Order is environment → keyring → restricted file. Secrets get their own precedence
because a CI job exporting OPENAI_API_KEY must win over whatever was stored locally.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ...types.provider import PROVIDER_ENV_VARS, Provider
from ..errors.failures import InvalidProviderEnvironmentKey
from .provider_credentials import ProviderCredentials
from .provider_store import ProviderCredentialStore

_MAX_KEY_CHARACTERS = 4096


class ProviderSource(StrEnum):
    """Stable non-secret provenance for a resolved provider credential."""

    ENVIRONMENT = "environment"
    KEYRING = "keyring"
    RESTRICTED_FILE = "restricted_file"


@dataclass(frozen=True)
class ResolvedProviderCredential:
    """Secret-safe credential plus non-secret provenance."""

    credentials: ProviderCredentials
    source: ProviderSource


class ProviderResolver:
    """Read one scoped provider credential according to documented precedence."""

    def __init__(self, store: ProviderCredentialStore, environment: Mapping[str, str]) -> None:
        # Store and environment injected for test control.
        self._store = store
        self._environment = environment

    def resolve(self, profile: str, provider: Provider) -> ResolvedProviderCredential | None:
        # Env var is highest; set-but-unusable is an error, not a silent miss.
        env_var = PROVIDER_ENV_VARS[provider]
        environment_value = self._environment.get(env_var)
        if environment_value is not None:
            token = environment_value.strip()
            if not token or len(token) > _MAX_KEY_CHARACTERS:
                raise InvalidProviderEnvironmentKey(provider.value, env_var)
            if not ProviderCredentials.is_live_format(provider, token):
                raise InvalidProviderEnvironmentKey(provider.value, env_var)
            return ResolvedProviderCredential(
                ProviderCredentials(provider=provider, api_key=token),  # type: ignore[arg-type]
                ProviderSource.ENVIRONMENT,
            )
        keyring_value = self._store.keyring.read(profile, provider)
        if keyring_value is not None:
            return ResolvedProviderCredential(keyring_value, ProviderSource.KEYRING)
        file_value = self._store.file.read(profile, provider)
        if file_value is not None:
            return ResolvedProviderCredential(file_value, ProviderSource.RESTRICTED_FILE)
        return None
