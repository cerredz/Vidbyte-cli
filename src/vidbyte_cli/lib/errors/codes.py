"""FILE: src/vidbyte_cli/lib/errors/codes.py

PURPOSE: Defines the stable error identifiers and process statuses emitted by the CLI.
These values are public automation contracts. Exception mapping and message rendering do
not belong here.

ROLE IN CODEBASE: CliError carries one CliErrorCode and ExitCode. ErrorHandler maps foreign
exceptions into this vocabulary, while OutputManager serializes the values for machine
consumers. Feature slices may select existing codes but must not invent string literals.

ARCHITECTURE NOTE: Keeping error identity separate from prose lets scripts branch on a
stable code while human messages and recovery hints improve independently.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CliErrorCode: stable machine-readable failure categories.
- ExitCode: documented process exit statuses shared by every command.

COMMON MODIFICATION PATTERNS: Add a code only for a distinct recovery action or automation
branch, document it in docs/architecture.md, and preserve every existing serialized value.

WHAT NOT TO DO IN THIS FILE:
1. Do not include backend exception names or provider-specific diagnostics.
2. Do not assign a new exit status when an existing documented category is sufficient.
3. Do not store user-facing prose in enum values.
4. Do not renumber an existing ExitCode.

KNOWN EDGE CASES: Multiple error codes intentionally share OPERATIONAL_FAILURE because exit
statuses are coarse shell signals while codes provide precise machine semantics.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines the public error and exit contracts.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py verifies representative error statuses and structured output.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class CliErrorCode(StrEnum):
    """Stable failure identity for users and automation."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"
    API_UNAVAILABLE = "API_UNAVAILABLE"
    API_PROTOCOL_ERROR = "API_PROTOCOL_ERROR"
    OPERATION_FAILED = "OPERATION_FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERRUPTED = "INTERRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ExitCode(IntEnum):
    """Stable shell statuses documented by the CLI."""

    SUCCESS = 0
    OPERATIONAL_FAILURE = 1
    USAGE = 2
    PARTIAL_OUTCOME = 3
    AUTHENTICATION = 4
    CREDIT_EXHAUSTED = 5
    SOFTWARE = 70
    INTERRUPTED = 130
