"""FILE: src/vidbyte_cli/lib/polling/poller.py

PURPOSE: Implements bounded, cancellation-aware polling with duplicate-transition
suppression and injectable clock/sleeper behavior.

ROLE IN CODEBASE: Generic harness waiting and later research watching adapt typed gateways
to PollTarget instead of duplicating wait loops.

ARCHITECTURE NOTE: Cancellation ends only the local wait. The accepted remote operation and
journal record remain intact for a recovery command.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from ..runtime.clock import InterruptibleSleeper, MonotonicClock
from ..runtime.signals import CancellationSignal

TValue = TypeVar("TValue")
TObserved = TypeVar("TObserved", contravariant=True)


class PollTarget(Protocol[TValue]):
    def fetch(self) -> TValue: ...

    def is_terminal(self, value: TValue) -> bool: ...

    def fingerprint(self, value: TValue) -> str: ...

    def suggested_delay(self, value: TValue) -> float | None: ...


class PollObserver(Protocol[TObserved]):
    def transition(self, value: TObserved) -> None: ...


@dataclass(frozen=True)
class PollOptions:
    interval_seconds: float = 2.0
    maximum_interval_seconds: float = 10.0
    timeout_seconds: float | None = None


class PollStopReason(StrEnum):
    TERMINAL = "terminal"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class PollResult(Generic[TValue]):
    value: TValue | None
    reason: PollStopReason


class Poller:
    """Generic synchronous watcher for durable remote resources."""

    def __init__(
        self,
        clock: MonotonicClock | None = None,
        sleeper: InterruptibleSleeper | None = None,
    ) -> None:
        self._clock = clock or MonotonicClock()
        self._sleeper = sleeper or InterruptibleSleeper()

    def watch(
        self,
        target: PollTarget[TValue],
        observer: PollObserver[TValue],
        options: PollOptions,
        cancellation: CancellationSignal,
    ) -> PollResult[TValue]:
        started = self._clock.now()
        last_fingerprint: str | None = None
        last_value: TValue | None = None
        while not cancellation.cancelled():
            if self._timed_out(started, options):
                return PollResult(last_value, PollStopReason.TIMED_OUT)
            value = target.fetch()
            last_value = value
            fingerprint = target.fingerprint(value)
            if fingerprint != last_fingerprint:
                observer.transition(value)
                last_fingerprint = fingerprint
            if target.is_terminal(value):
                return PollResult(value, PollStopReason.TERMINAL)
            delay = target.suggested_delay(value) or options.interval_seconds
            delay = min(max(0.0, delay), options.maximum_interval_seconds)
            if not self._sleeper.sleep(delay, cancellation):
                break
        return PollResult(last_value, PollStopReason.CANCELLED)

    def _timed_out(self, started: float, options: PollOptions) -> bool:
        return (
            options.timeout_seconds is not None
            and self._clock.now() - started >= options.timeout_seconds
        )
