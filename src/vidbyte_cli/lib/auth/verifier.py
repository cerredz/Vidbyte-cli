"""FILE: src/vidbyte_cli/lib/auth/verifier.py

PURPOSE: Defines and implements the verify-before-persist boundary used by login.

ROLE IN CODEBASE: LoginCommand calls CredentialVerifier before CredentialStore.write.
ApplicationContext supplies the implementation lazily.

ARCHITECTURE NOTE: The protocol makes the security invariant explicit: a credential cannot
reach durable storage unless verification returns successfully.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CredentialVerifier.verify(credentials, config) -> None: proves a token is accepted.
- PendingCredentialVerifier: safe stack seam until PR 4 supplies HTTP.

WHAT NOT TO DO IN THIS FILE:
1. Do not persist credentials.
2. Do not consider syntactic validation equivalent to server verification.
3. Do not expose a rejected token or backend response body.
4. Do not add HTTP retry policy in this PR.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import Protocol

from ..api.client import ApiClient
from ..api.endpoints.auth import AuthEndpoints
from ..config import ResolvedConfig
from ..errors import CliError, CliErrorCode
from .credentials import Credentials


class CredentialVerifier(Protocol):
    def verify(self, credentials: Credentials, config: ResolvedConfig) -> None: ...


class PendingCredentialVerifier:
    """Explicit seam completed by the reusable HTTP platform in PR 4."""

    def verify(self, credentials: Credentials, config: ResolvedConfig) -> None:
        del credentials, config
        raise CliError(
            CliErrorCode.API_UNAVAILABLE,
            "Credential verification is unavailable in this CLI build.",
            hint="Upgrade to the release that includes the reusable HTTP client.",
            retryable=False,
        )


class ApiCredentialVerifier:
    """Verify a candidate credential through /auth/whoami before storage."""

    def verify(self, credentials: Credentials, config: ResolvedConfig) -> None:
        with ApiClient(
            config.api_url,
            credentials.secret_value(),
            timeout_seconds=config.request_timeout_seconds,
        ) as client:
            AuthEndpoints(client).whoami()
