"""FILE: src/vidbyte_cli/lib/auth/resolver.py

PURPOSE: Resolves a credential for one profile/API origin in the strict order environment,
OS keyring, then permission-restricted fallback file while preserving safe provenance.

ROLE IN CODEBASE: API client factories and doctor consume ResolvedCredential. Login does
not use this resolver for persistence, preventing environment tokens from being saved.

ARCHITECTURE NOTE: The environment mapping is injected per invocation. The resolved model
stores a secret-safe Credentials object and a non-secret source label.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CredentialSource: stable non-secret provenance.
- ResolvedCredential: secret plus provenance.
- CredentialResolver.resolve(profile, api_url) -> ResolvedCredential | None.

WHAT NOT TO DO IN THIS FILE:
1. Do not mutate any credential store.
2. Do not include the environment token in diagnostics or model serialization.
3. Do not change precedence without updating docs and automation contracts.
4. Do not fall back from a keyring operational failure by hiding that failure.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ..errors import CliError, CliErrorCode
from .credentials import Credentials, CredentialStore


class CredentialSource(StrEnum):
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

    def __init__(
        self,
        store: CredentialStore,
        environment: Mapping[str, str],
    ) -> None:
        self._store = store
        self._environment = environment

    def resolve(self, profile: str, api_url: str) -> ResolvedCredential | None:
        environment_value = self._environment.get("VIDBYTE_API_KEY")
        if environment_value is not None:
            token = environment_value.strip()
            if not token or len(token) > 4096:
                raise CliError(
                    CliErrorCode.AUTH_REQUIRED,
                    "VIDBYTE_API_KEY is empty or invalid.",
                    hint="Set a valid key or remove the variable to use stored credentials.",
                )
            return ResolvedCredential(
                Credentials.from_value(token),
                CredentialSource.ENVIRONMENT,
            )
        keyring_value = self._store.keyring.read(profile, api_url)
        if keyring_value is not None:
            return ResolvedCredential(keyring_value, CredentialSource.KEYRING)
        file_value = self._store.file.read(profile, api_url)
        if file_value is not None:
            return ResolvedCredential(file_value, CredentialSource.RESTRICTED_FILE)
        return None
