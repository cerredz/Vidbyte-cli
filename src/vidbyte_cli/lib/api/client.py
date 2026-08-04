"""Typed HTTP client for the Vidbyte public API.

Owns the base URL, API-key header injection, and response-envelope unwrapping. Commands
and harnesses never call httpx directly — all HTTP goes through a typed endpoint group
built on this client.
"""

from __future__ import annotations

import os
from typing import TypeVar

from pydantic import BaseModel

from ..errors.failures import NotImplementedFeature

DEFAULT_API_URL = "https://api.vidbyte.ai"

TModel = TypeVar("TModel", bound=BaseModel)


class ApiClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        # Resolves the API host from the argument, then VIDBYTE_API_URL, then production.
        self.base_url = base_url or os.environ.get("VIDBYTE_API_URL") or DEFAULT_API_URL
        # The key is a secret: it is held here only to set the auth header, never logged.
        self._api_key = api_key or os.environ.get("VIDBYTE_API_KEY")

    def get(self, path: str, model: type[TModel]) -> TModel:
        # Performs an authenticated GET, unwraps the envelope, validates into `model`.
        raise NotImplementedFeature("api client requests")

    def get_list(self, path: str, model: type[TModel]) -> list[TModel]:
        # GET returning a list payload, each item validated into `model`.
        raise NotImplementedFeature("api client requests")

    def post(self, path: str, body: BaseModel, model: type[TModel]) -> TModel:
        # Performs an authenticated POST, unwraps the envelope, validates into `model`.
        raise NotImplementedFeature("api client requests")
