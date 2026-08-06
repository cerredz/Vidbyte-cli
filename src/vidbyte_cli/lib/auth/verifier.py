"""The verify-before-persist boundary login must cross before a key reaches storage.

Making it a protocol states the invariant in the type system: `CredentialStore.write` is
only ever reached through a `verify` that returned. A syntactically valid token is not a
working one, and a stored bad key fails every later command with no obvious cause.

The HTTP-backed implementation arrives with the reusable networking platform. Until then
this seam fails closed — refusing to log in is correct, storing unverified is not.
"""

from __future__ import annotations

from typing import Protocol

from ..config import ResolvedConfig
from ..errors.failures import CredentialVerificationUnavailable
from .credentials import Credentials


class CredentialVerifier(Protocol):
    def verify(self, credentials: Credentials, config: ResolvedConfig) -> None: ...


class PendingCredentialVerifier:
    """Explicit seam completed by the reusable HTTP platform."""

    def verify(self, credentials: Credentials, config: ResolvedConfig) -> None:
        del credentials, config
        raise CredentialVerificationUnavailable()
