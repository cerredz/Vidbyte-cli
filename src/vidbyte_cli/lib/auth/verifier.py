"""The verify-before-persist boundary login must cross before a key reaches storage.

Making it a protocol states the invariant in the type system: `CredentialStore.write` is
only ever reached through a `verify` that returned. A syntactically valid token is not a
working one, and a stored bad key fails every later command with no obvious cause.

`verify` returns the identity rather than nothing so `login` and `whoami` can share one call:
login discards the result, whoami prints it. Two commands asking the same question of the
backend cannot then drift into asking it two different ways.
"""

from __future__ import annotations

from typing import Protocol

from ...types.api import KeyIdentity
from ..api.client import ApiClient
from ..api.endpoints.auth import AuthEndpoints
from ..config import ResolvedConfig
from ..errors.failures import ApiProtocolError
from .credentials import Credentials


class CredentialVerifier(Protocol):
    def verify(self, credentials: Credentials, config: ResolvedConfig) -> KeyIdentity: ...


class ApiCredentialVerifier:
    """Prove a candidate key against the backend before it may be persisted."""

    def verify(self, credentials: Credentials, config: ResolvedConfig) -> KeyIdentity:
        # Calls the permission-free liveness check and returns the non-secret identity.
        identity = AuthEndpoints(ApiClient(config, credentials)).validate()
        if not identity.success:
            # A success status that denies success is a contract this CLI cannot act on, and
            # treating it as acceptance would store a key the backend has just refused.
            raise ApiProtocolError()
        return identity
