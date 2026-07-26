"""FILE: src/vidbyte_cli/lib/harness/errors.py

PURPOSE: Normalizes failures escaping the generic harness backend lifecycle into safe typed
CLI errors. Provider- and transport-specific classification lands here only after the
transport platform exists.

ROLE IN CODEBASE: BaseHarness dispatch preserves existing CliError values and sends every
other exception to map_harness_error(). ErrorHandler later renders the safe result.

ARCHITECTURE NOTE: The private cause is retained for redacted debugging, but its string
value never becomes user-facing prose.

FUNCTION INVENTORY (reviewed 2026-07-26):
- map_harness_error(error) -> CliError: produces one safe generic operational failure.

COMMON MODIFICATION PATTERNS: Add typed transport mappings without exposing response bodies
and keep generic fallback prose independent of exception values.

WHAT NOT TO DO IN THIS FILE:
1. Do not stringify an unknown exception into the message.
2. Do not render, log, or terminate.
3. Do not attach API keys, full prompts, or response bodies.
4. Do not add research-specific domain mappings.

KNOWN EDGE CASES: CliError passthrough preserves already-classified usage, authentication,
and credit failures. Unknown errors remain retryable operational failures.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines safe error normalization.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py verifies safe failure rendering at the public boundary.
"""

from __future__ import annotations

from ..errors.cli_error import CliError
from ..errors.codes import CliErrorCode


def map_harness_error(error: Exception) -> CliError:
    # Turns any non-CliError into safe generic prose while retaining the private cause for
    # later typed transport mapping. Never stringify a backend exception at this boundary.
    if isinstance(error, CliError):
        return error
    return CliError(
        CliErrorCode.OPERATION_FAILED,
        "The harness invocation failed.",
        hint="Retry the command. If the problem continues, use --debug for redacted details.",
        retryable=True,
        cause=error,
    )
