"""Typed wrappers for authentication-related backend routes."""

from __future__ import annotations

from ....types.api import WhoAmI
from ..client import ApiClient


class AuthEndpoints:
    def __init__(self, client: ApiClient) -> None:
        # Binds the endpoint group to a configured ApiClient.
        self._client = client

    def whoami(self) -> WhoAmI:
        # GET /auth/whoami — resolves the identity behind the configured API key.
        return self._client.get("/auth/whoami", WhoAmI)
