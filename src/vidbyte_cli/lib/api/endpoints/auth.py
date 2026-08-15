"""The one authentication route the CLI calls, and the identity it returns.

`validate` is the only permission-free liveness check the backend serves. It is chosen over a
cheap authenticated resource read because the API grants read and write scopes separately: a
key scoped only to write is perfectly valid, and a read-based check would refuse to log it in.
Capability belongs at the point of use, where a rejection can name the missing scope.
"""

from __future__ import annotations

from ....types.api import KeyIdentity
from ..client import ApiClient

AUTH_VALIDATE_PATH = "/api/skills/auth/validate"


class AuthEndpoints:
    def __init__(self, client: ApiClient) -> None:
        # Binds the endpoint group to a configured ApiClient.
        self._client = client

    def validate(self) -> KeyIdentity:
        # Proves the configured key is live and returns its non-secret identity.
        return self._client.post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
