"""FILE: src/vidbyte_cli/lib/errors/handler.py

PURPOSE: Maps every exception escaping command dispatch to safe output and a stable process
status. It is the sole application-level failure boundary; feature services should raise
typed failures rather than render them.

ROLE IN CODEBASE: CliApplication catches boundary exceptions and delegates here.
OutputManager renders mapped CliError values. Click, interrupts, broken pipes, and internal
bugs are normalized without exposing exception values.

ARCHITECTURE NOTE: Debug mode may show a redacted frame trace, but not exception messages,
locals, causes, request bodies, credentials, or full prompts.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ErrorHandler.handle(error) -> int: maps, renders, and returns one process status.

COMMON MODIFICATION PATTERNS: Add a foreign exception mapping only when it is platform-wide,
keep the user message generic, and preserve detailed causes privately.

WHAT NOT TO DO IN THIS FILE:
1. Do not stringify unexpected exceptions into user output.
2. Do not print tracebacks outside explicit debug mode.
3. Do not include traceback locals or exception values in debug diagnostics.
4. Do not special-case research domain failures; feature adapters map those to CliError.
5. Do not call sys.exit.

KNOWN EDGE CASES: Broken stdout pipes return success because the downstream consumer closed
normally. Ctrl-C and Click aborts return 130. A failure while rendering an error must not be
recursively handled here.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines safe failures and the stable exit table.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises usage, structured error, and interrupt-compatible statuses.
"""

from __future__ import annotations

import traceback

import click

from ..output.manager import OutputManager
from .cli_error import CliError
from .codes import CliErrorCode, ExitCode


class ErrorHandler:
    """Central conversion from boundary exceptions to safe CLI failures."""

    def __init__(self, output: OutputManager, debug: bool = False) -> None:
        self._output = output
        self._debug = debug

    def handle(self, error: BaseException) -> int:
        # Broken pipes are a successful shell-consumer closure and require no diagnostic.
        if isinstance(error, BrokenPipeError):
            return int(ExitCode.SUCCESS)
        mapped = self._map(error)
        self._output.error(mapped)
        trace_target: BaseException | None = mapped.cause
        if trace_target is None and mapped.code is CliErrorCode.INTERNAL_ERROR:
            trace_target = error
        if self._debug and trace_target is not None:
            self._render_redacted_trace(trace_target)
        return mapped.exit_code

    def _map(self, error: BaseException) -> CliError:
        # Preserve only errors explicitly declared safe by an application boundary.
        if isinstance(error, CliError):
            return error
        if isinstance(error, click.ClickException):
            return self._map_click(error)
        if isinstance(error, (click.exceptions.Abort, KeyboardInterrupt)):
            return CliError(
                CliErrorCode.INTERRUPTED,
                "Operation interrupted.",
                ExitCode.INTERRUPTED,
            )
        cause = error if isinstance(error, Exception) else None
        return CliError(
            CliErrorCode.INTERNAL_ERROR,
            "An unexpected internal error occurred.",
            ExitCode.SOFTWARE,
            hint="Retry with --debug for a redacted stack trace.",
            cause=cause,
        )

    def _map_click(self, error: click.ClickException) -> CliError:
        # Click prose is limited to parser-owned values and is safe for invalid invocation help.
        context = error.ctx if isinstance(error, click.UsageError) else None
        command_path = context.command_path if context is not None else "vidbyte-cli"
        return CliError(
            CliErrorCode.INVALID_ARGUMENT,
            error.format_message(),
            error.exit_code,
            hint=f"Run '{command_path} --help' for usage.",
            cause=error,
        )

    def _render_redacted_trace(self, error: BaseException) -> None:
        # Format stack frames only; exception values and chained causes may contain secrets.
        self._output.diagnostic("Debug traceback (exception values redacted):")
        if error.__traceback__ is None:
            self._output.diagnostic(f"  {type(error).__module__}.{type(error).__qualname__}")
            return
        for line in traceback.format_tb(error.__traceback__):
            self._output.diagnostic(line.rstrip())
