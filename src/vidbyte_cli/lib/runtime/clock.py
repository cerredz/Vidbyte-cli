"""FILE: src/vidbyte_cli/lib/runtime/clock.py

PURPOSE: Supplies injectable monotonic time and cancellation-aware sleeping.

ROLE IN CODEBASE: Retry and polling policies use this boundary instead of embedding
uninterruptible sleeps or wall-clock deadline arithmetic.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import time

from .signals import CancellationSignal


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


class InterruptibleSleeper:
    def sleep(self, seconds: float, signal: CancellationSignal) -> bool:
        """Wait up to seconds; return False when cancellation wakes the wait."""
        return not signal.wait(max(0.0, seconds))
