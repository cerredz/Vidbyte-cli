"""FILE: src/vidbyte_cli/lib/runtime/signals.py

PURPOSE: Converts process termination signals into cooperative local cancellation state.

ROLE IN CODEBASE: Pollers and request loops inspect CancellationSignal. SignalScope installs
and restores handlers only on the main thread and never calls a remote cancel route.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import signal
import threading
from types import FrameType
from typing import Any


class CancellationSignal:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, seconds: float) -> bool:
        return self._event.wait(seconds)


class SignalScope:
    """Temporarily map SIGINT/SIGTERM to cooperative cancellation."""

    def __init__(self, cancellation: CancellationSignal) -> None:
        self._cancellation = cancellation
        self._previous: dict[int, Any] = {}

    def __enter__(self) -> SignalScope:
        if threading.current_thread() is not threading.main_thread():
            return self
        for number in self._supported_signals():
            self._previous[number] = signal.getsignal(number)
            signal.signal(number, self._handle)
        return self

    def __exit__(self, *_: object) -> None:
        for number, handler in self._previous.items():
            signal.signal(number, handler)
        self._previous.clear()

    def _handle(self, signum: int, frame: FrameType | None) -> None:
        del signum, frame
        self._cancellation.cancel()

    def _supported_signals(self) -> tuple[int, ...]:
        values = [signal.SIGINT]
        if hasattr(signal, "SIGTERM"):
            values.append(signal.SIGTERM)
        return tuple(values)
