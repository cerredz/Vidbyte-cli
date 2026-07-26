"""FILE: src/vidbyte_cli/lib/errors/cli_error.py

PURPOSE: Defines the user-safe exception passed from command and service boundaries to the
central runtime handler. It carries stable automation semantics and recovery metadata while
retaining an optional private cause for diagnostics.

ROLE IN CODEBASE: Commands and services raise CliError instead of printing or terminating.
ErrorHandler renders it through OutputManager and returns its exit status. codes.py owns
the serialized vocabulary.

ARCHITECTURE NOTE: A CliError message is safe to display, but its cause is not. This split
prevents backend, credential, prompt, or filesystem details from leaking into normal output.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CliError(...) -> CliError: captures a stable code, safe message, and recovery metadata.
- not_implemented(subject) -> CliError: creates a consistent scaffold failure.
- usage_error(message, hint) -> CliError: creates a typed command-usage failure.

COMMON MODIFICATION PATTERNS: Add structured metadata only when OutputManager can serialize
it safely and every error mapper can populate it consistently.

WHAT NOT TO DO IN THIS FILE:
1. Do not derive the safe message by stringifying cause.
2. Do not render, log, or print the error.
3. Do not attach API keys, full prompts, authorization headers, or response bodies.
4. Do not create feature-specific subclasses when a stable code is sufficient.

KNOWN EDGE CASES: cause may contain sensitive implementation detail and is therefore never
included in human or machine output. Debug traces redact exception values.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines the typed error boundary and exit table.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises safe human and machine usage-error rendering.
"""

from __future__ import annotations

from .codes import CliErrorCode, ExitCode


class CliError(Exception):
    """A classified CLI failure whose message and metadata are safe to display."""

    def __init__(
        self,
        code: CliErrorCode,
        message: str,
        exit_code: int = ExitCode.OPERATIONAL_FAILURE,
        *,
        hint: str | None = None,
        retryable: bool = False,
        request_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        # Store the private cause separately so normal rendering cannot expose it by accident.
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = int(exit_code)
        self.hint = hint
        self.retryable = retryable
        self.request_id = request_id
        self.cause = cause

    @property
    def code_value(self) -> str:
        # Output protocols depend on a plain string without importing this enum package.
        return self.code.value


def not_implemented(subject: str) -> CliError:
    # Standard stub error for scaffolded behavior that is not built yet.
    return CliError(
        CliErrorCode.NOT_IMPLEMENTED,
        f"{subject} is not implemented yet.",
        hint="Check the CLI release notes for availability.",
    )


def usage_error(message: str, hint: str | None = None) -> CliError:
    # Central construction keeps invalid-input failures branchable by code and exit status.
    return CliError(CliErrorCode.INVALID_ARGUMENT, message, ExitCode.USAGE, hint=hint)
