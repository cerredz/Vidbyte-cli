"""The single boundary where an exception becomes safe output and a process status.

One match statement classifies everything that can reach `CliApplication.run`, so the set of
exception kinds the CLI understands is readable in one place. Anything unmatched is a CLI
defect, not a user mistake, and is reported without quoting the exception value — a foreign
exception string may hold a credential, a prompt, or a backend response body.

Debug mode adds stack frames only. Never locals, never exception values, never causes.
"""

from __future__ import annotations

import traceback

import click

from ..output.manager import OutputManager
from .cli_error import CliError
from .codes import ExitCode
from .failures import InvalidCommandUsage, OperationInterrupted, UnexpectedInternalError


class ErrorHandler:
    """Central conversion from boundary exceptions to safe CLI failures."""

    def __init__(self, output: OutputManager, debug: bool = False) -> None:
        self._output = output
        self._debug = debug

    def handle(self, error: BaseException) -> int:
        # UsageError precedes ClickException because it is the more specific subclass.
        match error:
            case BrokenPipeError():
                # A closed downstream pipe is a normal shell outcome, not a failure.
                return int(ExitCode.SUCCESS)
            case CliError():
                return self._report(error, error)
            case click.UsageError():
                context = error.ctx
                path = context.command_path if context is not None else "vidbyte-cli"
                return self._report(
                    InvalidCommandUsage(error.format_message(), path, error.exit_code, error),
                    error,
                )
            case click.ClickException():
                return self._report(
                    InvalidCommandUsage(
                        error.format_message(), "vidbyte-cli", error.exit_code, error
                    ),
                    error,
                )
            case click.exceptions.Abort() | KeyboardInterrupt():
                return self._report(OperationInterrupted(), error)
            case _:
                cause = error if isinstance(error, Exception) else None
                return self._report(UnexpectedInternalError(cause), error)

    def _report(self, mapped: CliError, original: BaseException) -> int:
        # Render once, then optionally add frames from whichever exception carries them.
        self._output.error(mapped)
        if self._debug:
            self._render_redacted_trace(mapped.cause or original)
        return mapped.exit_code

    def _render_redacted_trace(self, error: BaseException) -> None:
        # Format stack frames only; exception values and chained causes may hold secrets.
        self._output.diagnostic("Debug traceback (exception values redacted):")
        if error.__traceback__ is None:
            self._output.diagnostic(f"  {type(error).__module__}.{type(error).__qualname__}")
            return
        for line in traceback.format_tb(error.__traceback__):
            self._output.diagnostic(line.rstrip())
