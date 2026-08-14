"""Typed HTTP client for the Vidbyte public API.

Owns the base URL, API-key header injection, and response-envelope unwrapping. Commands
and harnesses never call httpx directly — all HTTP goes through a typed endpoint group
built on this client.

Settings and the credential arrive already resolved, so this client never reads the
environment: doing so would let a stale variable outrank an explicit option and would skip
the origin validation that `ResolvedConfig.api_url` has already passed.

One request is serialized once and re-issued byte-identically under the same idempotency
key, because every retry of a priced mutation must be the same mutation.
"""

from __future__ import annotations

import time
from typing import TypeVar

import httpx
from pydantic import BaseModel

from ..auth.credentials import Credentials
from ..config import ResolvedConfig
from ..errors.failures import ApiRouteMisconfigured
from ..runtime.version import current_version
from .problem import ApiProblemMapper
from .response import ResponseDecoder, ResponseShape
from .retry import RequestMetadata, RequestOutcome, RetryPolicy

# The backend reads this header first and accepts `Authorization: Bearer` only as a fallback,
# so the key travels here and nowhere else. Sending both would be worse than sending one: the
# gatekeeper stops at a malformed `x-api-key` instead of falling through to the bearer value.
API_KEY_HEADER_NAME = "x-api-key"
_MAX_CONNECTIONS = 20
_MAX_KEEPALIVE_CONNECTIONS = 10

TModel = TypeVar("TModel", bound=BaseModel)


class ApiClient:
    def __init__(self, config: ResolvedConfig, credentials: Credentials) -> None:
        # Takes the invocation's resolved host, timeout, and secret; resolves nothing itself.
        self.base_url = config.api_url.rstrip("/")
        self.timeout_seconds = config.request_timeout_seconds
        # The key is a secret: it is held here only to set the auth header, never logged.
        self._credentials = credentials
        # Built on first send, so constructing a client opens no socket and `--help` is free.
        self._transport: httpx.Client | None = None
        self._retry = RetryPolicy()
        self._decoder = ResponseDecoder()
        self._problems = ApiProblemMapper()

    def auth_headers(self) -> dict[str, str]:
        # The single point where the stored secret is unwrapped for transmission.
        return {API_KEY_HEADER_NAME: self._credentials.secret_value()}

    def get(
        self,
        path: str,
        model: type[TModel],
        *,
        shape: ResponseShape = ResponseShape.ENVELOPE,
    ) -> TModel:
        # Performs an authenticated GET, unwraps the declared shape, validates into `model`.
        return self.request("GET", path, response_model=model, response_shape=shape)

    def get_list(self, path: str, model: type[TModel]) -> list[TModel]:
        # GET returning an enveloped list payload, each item validated into `model`.
        response = self._send("GET", path, None, None)
        return self._decoder.many(response, model)

    def post(
        self,
        path: str,
        body: BaseModel,
        model: type[TModel],
        *,
        shape: ResponseShape = ResponseShape.ENVELOPE,
        idempotency_key: str | None = None,
    ) -> TModel:
        # Performs an authenticated POST, unwraps the declared shape, validates into `model`.
        return self.request(
            "POST",
            path,
            response_model=model,
            response_shape=shape,
            body=body,
            idempotency_key=idempotency_key,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        response_model: type[TModel],
        response_shape: ResponseShape,
        body: BaseModel | None = None,
        idempotency_key: str | None = None,
    ) -> TModel:
        # The one path every typed request takes: send with retries, then decode.
        response = self._send(method, path, body, idempotency_key)
        return self._decoder.one(response, response_model, response_shape)

    def close(self) -> None:
        # Releases the connection pool; safe to call when no request was ever made.
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def _send(
        self,
        method: str,
        path: str,
        body: BaseModel | None,
        idempotency_key: str | None,
    ) -> httpx.Response:
        # Re-issues one identical request while the retry policy allows, then classifies.
        url = self._url(path)
        content = self._content(body)
        headers = self._headers(idempotency_key, body is not None)
        metadata = RequestMetadata(method.upper(), idempotency_key is not None)
        attempt = 1
        while True:
            outcome = self._attempt(method, url, content, headers)
            decision = self._retry.decide(metadata, attempt, outcome)
            if not decision.retry:
                return self._settle(outcome)
            time.sleep(decision.delay_seconds)
            attempt += 1

    def _attempt(
        self,
        method: str,
        url: str,
        content: bytes | None,
        headers: dict[str, str],
    ) -> RequestOutcome:
        # One attempt is either a reply or a transport failure, never both and never neither.
        try:
            return self._client().request(method, url, content=content, headers=headers)
        except httpx.HTTPError as error:
            return error

    def _settle(self, outcome: RequestOutcome) -> httpx.Response:
        # The retry policy has given up, so this outcome is the caller's answer.
        if isinstance(outcome, httpx.HTTPError):
            raise self._problems.from_transport(outcome) from outcome
        if not 200 <= outcome.status_code < 300:
            raise self._problems.from_response(outcome)
        return outcome

    def _client(self) -> httpx.Client:
        # Built once per invocation so a watch loop reuses one pool across many polls.
        if self._transport is None:
            self._transport = httpx.Client(
                timeout=httpx.Timeout(self.timeout_seconds),
                limits=httpx.Limits(
                    max_connections=_MAX_CONNECTIONS,
                    max_keepalive_connections=_MAX_KEEPALIVE_CONNECTIONS,
                ),
            )
        return self._transport

    def _content(self, body: BaseModel | None) -> bytes | None:
        # Serialized once so every attempt is byte-identical, and `exclude_none` is what
        # keeps unset options out of a request DTO the backend validates with extra="forbid".
        if body is None:
            return None
        return body.model_dump_json(exclude_none=True, by_alias=True).encode("utf-8")

    def _url(self, path: str) -> str:
        # A route carrying its own scheme or host would send the key to an unconfigured origin.
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ApiRouteMisconfigured()
        return f"{self.base_url}{path}"

    def _headers(self, idempotency_key: str | None, has_body: bool) -> dict[str, str]:
        # Identity, content negotiation, and the credential; nothing derived from user input.
        headers = {
            "Accept": "application/json",
            "User-Agent": f"vidbyte-cli/{current_version()}",
            **self.auth_headers(),
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers
