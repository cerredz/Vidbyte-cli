"""FILE: src/vidbyte_cli/lib/runtime/context.py

PURPOSE: Owns dependencies and presentation policy that live for exactly one CLI invocation
and creates expensive or stateful collaborators lazily. Commands obtain services through
Click's context rather than reaching for module globals.

ROLE IN CODEBASE: application.py creates ApplicationContext and places it on the Click root
context. The existing harness runtime is created through HarnessContext.default() only when
a harness namespace needs it. io/streams.py supplies the invocation's process channels.

ARCHITECTURE NOTE: This is the composition root's dependency container, not a service
locator shared across processes. Its invocation lifetime and lazy harness construction are
specified in docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- InvocationOptions: immutable root-option policy for one invocation.
- ApplicationContext(streams, factory) -> ApplicationContext: records lazy dependencies.
- ApplicationContext.configure(options) -> None: binds parsed root presentation policy.
- ApplicationContext.output() -> OutputManager: returns the invocation output boundary.
- ApplicationContext.error_handler() -> ErrorHandler: returns the central failure boundary.
- ApplicationContext.harness_context() -> HarnessContext: lazily returns one harness context.

COMMON MODIFICATION PATTERNS: Add a typed lazy property when a reusable platform service is
introduced, inject its factory, and add close() when the first invocation-owned closeable
collaborator is introduced.

WHAT NOT TO DO IN THIS FILE:
1. Do not execute API calls or command use cases; services and features own behavior.
2. Do not create dependencies at module import time.
3. Do not store context across invocations or threads.
4. Do not read environment variables directly; configuration resolvers own precedence.

KNOWN EDGE CASES: Help and version paths should not need credentials or network services.
Lazy construction preserves that property even when command registration inspects context.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines invocation dependency lifetime after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py covers offline help/version and dynamic static-harness registration.
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

_Factory = Callable[[], HarnessContext]


@dataclass(frozen=True)
class InvocationOptions:
    """Root presentation and interaction policy resolved before command execution."""

    output_format: OutputFormat = OutputFormat.HUMAN
    profile: str | None = None
    no_input: bool = False
    color: ColorMode = ColorMode.AUTO
    debug: bool = False


class ApplicationContext:
    """Invocation-owned dependency graph shared through Click context."""

    def __init__(self, streams: IOStreams, factory: _Factory | None = None) -> None:
        # Keep construction side-effect free; service factories run only when first requested.
        self.streams = streams
        self.options = InvocationOptions()
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output)
        self._harness_factory = factory or self._build_harness_context
        self._harness_context: HarnessContext | None = None

    def configure(self, options: InvocationOptions) -> None:
        # Root parsing occurs before any command service construction or output emission.
        if self._harness_context is not None:
            if options == self.options:
                return
            raise RuntimeError("Invocation options cannot change after harness construction.")
        self.options = options
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output, debug=options.debug)

    def output(self) -> OutputManager:
        # Callers share one policy object so stdout cardinality remains enforceable.
        return self._output

    def error_handler(self) -> ErrorHandler:
        # The handler is rebuilt only when root options are configured.
        return self._errors

    def harness_context(self) -> HarnessContext:
        # One invocation reuses one collaborator graph without leaking it into the next run.
        if self._harness_context is None:
            self._harness_context = self._harness_factory()
        return self._harness_context

    def _build_output(self) -> OutputManager:
        # Terminal detection is reevaluated after parsed color and no-input preferences.
        terminal_policy = TerminalPolicy(self.options.color, self.options.no_input)
        terminal = TerminalCapabilities.detect(self.streams, terminal_policy)
        return OutputManager(self.streams, OutputPolicy(self.options.output_format, terminal))

    def _build_harness_context(self) -> HarnessContext:
        # The legacy harness adapter shares the invocation's selected output contract.
        return HarnessContext.default(self._output)
