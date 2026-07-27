"""The dependency graph owned by exactly one invocation, attached to click's context.

Commands reach services through here instead of module globals. Everything expensive is
built lazily so `--help` and `--version` never touch credentials or the network.
"""

from __future__ import annotations

from collections.abc import Callable

from ..harness.context import HarnessContext
from ..io import IOStreams


class ApplicationContext:
    """Invocation-scoped services, shared with commands via click's context object."""

    def __init__(
        self,
        streams: IOStreams,
        harness_factory: Callable[[], HarnessContext] = HarnessContext.default,
    ) -> None:
        # Construction stays side-effect free; factories run on first request only.
        self.streams = streams
        self._harness_factory = harness_factory
        self._harness_context: HarnessContext | None = None

    def harness_context(self) -> HarnessContext:
        # One invocation reuses one graph, and never leaks it into the next run.
        if self._harness_context is None:
            self._harness_context = self._harness_factory()
        return self._harness_context
