"""FILE: src/vidbyte_cli/lib/api/client.py

PURPOSE: Executes typed Vidbyte HTTP requests with explicit timeouts, bounded safe retries,
stable request identity, response validation, redaction, and cancellation checks.

ROLE IN CODEBASE: Endpoint groups are the only callers. ApplicationContext owns one client
per invocation and closes it; login may create a short-lived candidate client.

ARCHITECTURE NOTE: One serialized body, idempotency key, and request ID are reused across
all attempts. POST without an idempotency key is never retried.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel

from ..errors import CliError, CliErrorCode
from ..runtime.version import current_version
from .problem import ApiProblemMapper
from .response import ResponseDecoder, ResponseShape
from .retry import RequestMetadata, RetryPolicy

DEFAULT_API_URL = "https://api.vidbyte.ai"
TModel = TypeVar("TModel", bound=BaseModel)


class CancellationProbe:
    """Small cancellation interface accepted without importing polling."""

    def cancelled(self) -> bool:
        return False


class ApiClient:
    """Synchronous typed client for one API origin and credential."""

    def __init__(
        self,
        base_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        diagnostic: Callable[[str], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._owns_client = client is None
        self._retry = retry_policy or RetryPolicy()
        self._sleep = sleeper
        self._diagnostic = diagnostic
        self._decoder = ResponseDecoder()
        self._problems = ApiProblemMapper()

    def get(
        self,
        path: str,
        model: type[TModel],
        *,
        shape: ResponseShape = ResponseShape.ENVELOPE,
        signal: CancellationProbe | None = None,
    ) -> TModel:
        return self.request("GET", path, response_model=model, response_shape=shape, signal=signal)

    def get_list(
        self,
        path: str,
        model: type[TModel],
        *,
        shape: ResponseShape = ResponseShape.LIST_ENVELOPE,
        signal: CancellationProbe | None = None,
    ) -> list[TModel]:
        response = self._send("GET", path, None, None, signal)
        return self._decoder.many(response, model, shape)

    def post(
        self,
        path: str,
        body: BaseModel,
        model: type[TModel],
        *,
        idempotency_key: str | None = None,
        shape: ResponseShape = ResponseShape.ENVELOPE,
        signal: CancellationProbe | None = None,
    ) -> TModel:
        return self.request(
            "POST",
            path,
            body=body,
            response_model=model,
            response_shape=shape,
            idempotency_key=idempotency_key,
            signal=signal,
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
        signal: CancellationProbe | None = None,
    ) -> TModel:
        response = self._send(method, path, body, idempotency_key, signal)
        return self._decoder.one(response, response_model, response_shape)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _send(
        self,
        method: str,
        path: str,
        body: BaseModel | None,
        idempotency_key: str | None,
        signal: CancellationProbe | None,
    ) -> httpx.Response:
        url = self._url(path)
        content = body.model_dump_json().encode("utf-8") if body is not None else None
        headers = self._headers(idempotency_key, body is not None)
        metadata = RequestMetadata(method.upper(), idempotency_key is not None)
        attempt = 1
        while True:
            if signal is not None and signal.cancelled():
                raise CliError(
                    CliErrorCode.INTERRUPTED,
                    "The local request was interrupted.",
                    130,
                )
            response: httpx.Response | None = None
            error: httpx.HTTPError | None = None
            try:
                response = self._client.request(method, url, content=content, headers=headers)
            except httpx.HTTPError as caught:
                error = caught
            decision = self._retry.decide(metadata, attempt, response, error)
            if decision.retry:
                if decision.delay_clamped and self._diagnostic is not None:
                    self._diagnostic("Server Retry-After was clamped to the local retry cap.")
                self._sleep(decision.delay_seconds)
                attempt += 1
                continue
            if error is not None:
                raise self._problems.from_transport(error) from error
            if response is None:
                raise RuntimeError("HTTP attempt produced no response or transport error.")
            if not 200 <= response.status_code < 300:
                raise self._problems.from_response(response)
            return response

    def _url(self, path: str) -> str:
        parsed = urlsplit(path)
        if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc:
            raise CliError(
                CliErrorCode.INTERNAL_ERROR,
                "An invalid API route was configured in the CLI.",
                70,
            )
        return f"{self.base_url}{path}"

    def _headers(self, idempotency_key: str | None, has_body: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Request-ID": str(uuid4()),
            "User-Agent": f"vidbyte-cli/{current_version()}",
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers
