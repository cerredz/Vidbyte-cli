"""The dependency graph and presentation policy owned by exactly one invocation.

Commands reach services through here instead of module globals. Everything expensive is
built lazily, so `--help` and `--version` never touch credentials or the network.

Root options arrive through `configure()` before any command service exists — output policy
has to be settled before the first byte is written, and before an optional harness context
can capture the wrong OutputManager.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..errors.handler import ErrorHandler
from ..harness.context import HarnessContext
from ..io import IOStreams
from ..io.terminal import TerminalCapabilities, TerminalPolicy
from ..output.formats import ColorMode, OutputFormat
from ..output.manager import OutputManager, OutputPolicy


@dataclass(frozen=True)
class InvocationOptions:
    """Root presentation and interaction policy resolved before command execution."""

    output_format: OutputFormat = OutputFormat.HUMAN
    profile: str | None = None
    no_input: bool = False
    color: ColorMode = ColorMode.AUTO
    debug: bool = False


class ApplicationContext:
    """Invocation-scoped services, shared with commands via click's context object."""

    def __init__(
        self,
        streams: IOStreams,
        harness_factory: Callable[[], HarnessContext] | None = None,
    ) -> None:
        # Construction stays side-effect free; factories run on first request only.
        self.streams = streams
        self.options = InvocationOptions()
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output)
        self._harness_factory = harness_factory or self._build_harness_context
        self._harness_context: HarnessContext | None = None

    def configure(self, options: InvocationOptions) -> None:
        # The harness context captured the current OutputManager, so changing policy after
        # it exists would leave two managers disagreeing about the same streams.
        if self._harness_context is not None:
            if options == self.options:
                return
            raise RuntimeError("Invocation options cannot change after harness construction.")
        self.options = options
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output, debug=options.debug)

    def output(self) -> OutputManager:
        # Callers share one policy object so stdout cardinality stays enforceable.
        return self._output

    def error_handler(self) -> ErrorHandler:
        return self._errors

    def harness_context(self) -> HarnessContext:
        # One invocation reuses one graph, and never leaks it into the next run.
        if self._harness_context is None:
            self._harness_context = self._harness_factory()
        return self._harness_context

    def _build_output(self) -> OutputManager:
        # Terminal detection reruns whenever color or no-input preferences change.
        terminal_policy = TerminalPolicy(self.options.color, self.options.no_input)
        terminal = TerminalCapabilities.detect(self.streams, terminal_policy)
        return OutputManager(self.streams, OutputPolicy(self.options.output_format, terminal))

    def _build_harness_context(self) -> HarnessContext:
        # The legacy harness adapter shares this invocation's selected output contract.
        return HarnessContext.default(self._output)
