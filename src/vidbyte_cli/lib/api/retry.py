"""FILE: src/vidbyte_cli/lib/api/retry.py

PURPOSE: Makes retry eligibility and bounded exponential delay explicit for HTTP requests.

ROLE IN CODEBASE: ApiClient asks RetryPolicy after transport failures and retryable statuses.
Unsafe POST requests are eligible only when one idempotency key is retained.

ARCHITECTURE NOTE: The policy is pure except for injected randomness and clock time.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import email.utils
import random
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx


@dataclass(frozen=True)
class RequestMetadata:
    method: str
    has_idempotency_key: bool = False


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_seconds: float = 0.0
    delay_clamped: bool = False


class RetryPolicy:
    """Three-attempt safe retry policy with exponential backoff and jitter."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        maximum_delay_seconds: float = 10.0,
        random_source: random.Random | None = None,
    ) -> None:
        self._max_attempts = max_attempts
        self._maximum_delay = maximum_delay_seconds
        self._random = random_source or random.Random()

    def decide(
        self,
        request: RequestMetadata,
        attempt: int,
        response: httpx.Response | None,
        error: Exception | None,
    ) -> RetryDecision:
        if attempt >= self._max_attempts or not self._method_is_safe(request):
            return RetryDecision(False)
        retryable_error = isinstance(
            error,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ),
        )
        retryable_response = response is not None and response.status_code in {
            408,
            429,
            502,
            503,
            504,
        }
        if not retryable_error and not retryable_response:
            return RetryDecision(False)
        server_delay = self._retry_after(response)
        if server_delay is not None:
            clamped = server_delay > self._maximum_delay
            return RetryDecision(True, min(server_delay, self._maximum_delay), clamped)
        delay = min(0.25 * (2 ** (attempt - 1)), 4.0) + self._random.uniform(0.0, 0.25)
        return RetryDecision(True, min(delay, self._maximum_delay))

    def _method_is_safe(self, request: RequestMetadata) -> bool:
        return request.method.upper() in {"GET", "HEAD", "OPTIONS"} or (
            request.method.upper() == "POST" and request.has_idempotency_key
        )

    def _retry_after(self, response: httpx.Response | None) -> float | None:
        if response is None:
            return None
        value = response.headers.get("retry-after")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            now = datetime.now(UTC)
            return max(0.0, (parsed.astimezone(UTC) - now).total_seconds())
