"""Typed HTTP client for the Vidbyte public API.

Owns the base URL, API-key header injection, and response-envelope unwrapping. Commands
and harnesses never call httpx directly — all HTTP goes through a typed endpoint group
built on this client.

Settings and the credential arrive already resolved, so this client never reads the
environment: doing so would let a stale variable outrank an explicit option and would skip
the origin validation that `ResolvedConfig.api_url` has already passed.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from ..auth.credentials import Credentials
from ..config import ResolvedConfig
from ..errors.failures import NotImplementedFeature

# The backend reads this header first and accepts `Authorization: Bearer` only as a fallback,
# so the key travels here and nowhere else. Sending both would be worse than sending one: the
# gatekeeper stops at a malformed `x-api-key` instead of falling through to the bearer value.
API_KEY_HEADER_NAME = "x-api-key"

TModel = TypeVar("TModel", bound=BaseModel)


class ApiClient:
    def __init__(self, config: ResolvedConfig, credentials: Credentials) -> None:
        # Takes the invocation's resolved host, timeout, and secret; resolves nothing itself.
        self.base_url = config.api_url
        self.timeout_seconds = config.request_timeout_seconds
        # The key is a secret: it is held here only to set the auth header, never logged.
        self._credentials = credentials

    def auth_headers(self) -> dict[str, str]:
        # The single point where the stored secret is unwrapped for transmission.
        return {API_KEY_HEADER_NAME: self._credentials.secret_value()}

    def get(self, path: str, model: type[TModel]) -> TModel:
        # Performs an authenticated GET, unwraps the envelope, validates into `model`.
        raise NotImplementedFeature("api client requests")

    def get_list(self, path: str, model: type[TModel]) -> list[TModel]:
        # GET returning a list payload, each item validated into `model`.
        raise NotImplementedFeature("api client requests")

    def post(self, path: str, body: BaseModel, model: type[TModel]) -> TModel:
        # Performs an authenticated POST, unwraps the envelope, validates into `model`.
        raise NotImplementedFeature("api client requests")
