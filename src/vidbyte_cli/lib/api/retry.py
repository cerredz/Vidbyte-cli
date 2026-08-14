"""Whether one failed attempt may be repeated, and how long to wait first.

Kept apart from the client so the rule is readable on its own: retrying a mutation is only
safe while an idempotency key makes the backend collapse duplicates, and every research
mutation is priced. A `POST` without that key is therefore never repeated, whatever failed.

This class decides; it never sleeps. The caller owns the wait, so the decision stays pure
apart from injected randomness.
"""

from __future__ import annotations

import email.utils
import random
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

_MAX_ATTEMPTS = 3
_MAXIMUM_DELAY_SECONDS = 10.0
_BASE_DELAY_SECONDS = 0.25
_UNJITTERED_CAP_SECONDS = 4.0
_JITTER_SECONDS = 0.25
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_RETRYABLE_STATUSES = frozenset({408, 429, 502, 503, 504})
_RETRYABLE_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


@dataclass(frozen=True)
class RequestMetadata:
    """The two facts about a request that decide whether repeating it is safe."""

    method: str
    has_idempotency_key: bool = False


# One attempt ends as exactly one of these, which is why they travel as a union rather than
# as a pair of nullable arguments nobody can see are mutually exclusive.
RequestOutcome = httpx.Response | httpx.HTTPError


@dataclass(frozen=True)
class RetryDecision:
    """One verdict, plus the wait the caller should perform before the next attempt."""

    retry: bool
    delay_seconds: float = 0.0
    delay_clamped: bool = False


class RetryPolicy:
    """Bounded safe-retry policy with exponential backoff and jitter."""

    def __init__(self, random_source: random.Random | None = None) -> None:
        # Randomness is injected so jitter can be made deterministic by a caller.
        self._random = random_source or random.Random()

    def decide(
        self,
        request: RequestMetadata,
        attempt: int,
        outcome: RequestOutcome,
    ) -> RetryDecision:
        # Answers whether this attempt may be repeated, and after how long.
        if attempt >= _MAX_ATTEMPTS or not self._is_repeatable(request):
            return RetryDecision(False)
        if not self._is_transient(outcome):
            return RetryDecision(False)
        return self._delay(attempt, outcome)

    def _is_repeatable(self, request: RequestMetadata) -> bool:
        # A priced mutation may only be repeated while a key makes the backend deduplicate.
        method = request.method.upper()
        return method in _SAFE_METHODS or (method == "POST" and request.has_idempotency_key)

    def _is_transient(self, outcome: RequestOutcome) -> bool:
        # Distinguishes a failure worth repeating from a rejection that will repeat itself.
        if isinstance(outcome, httpx.Response):
            return outcome.status_code in _RETRYABLE_STATUSES
        return isinstance(outcome, _RETRYABLE_ERRORS)

    def _delay(self, attempt: int, outcome: RequestOutcome) -> RetryDecision:
        # A server's own pacing wins over the local curve, up to the local ceiling.
        server_delay = self._retry_after(outcome)
        if server_delay is not None:
            clamped = server_delay > _MAXIMUM_DELAY_SECONDS
            return RetryDecision(True, min(server_delay, _MAXIMUM_DELAY_SECONDS), clamped)
        backoff = min(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), _UNJITTERED_CAP_SECONDS)
        jittered = backoff + self._random.uniform(0.0, _JITTER_SECONDS)
        return RetryDecision(True, min(jittered, _MAXIMUM_DELAY_SECONDS))

    def _retry_after(self, outcome: RequestOutcome) -> float | None:
        # Accepts both header forms; an unparseable value is ignored rather than read as 0.
        if not isinstance(outcome, httpx.Response):
            return None
        value = outcome.headers.get("retry-after")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return self._retry_after_date(value)

    def _retry_after_date(self, value: str) -> float | None:
        # An HTTP-date already in the past yields no wait rather than a negative one.
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, (parsed.astimezone(UTC) - datetime.now(UTC)).total_seconds())
