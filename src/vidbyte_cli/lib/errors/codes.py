"""The stable error and exit vocabulary the CLI publishes to shells and agents.

Every value here is a public contract: a shipped code string may not be reworded and a
shipped exit number may not be reassigned. Prose belongs to the `CliError` subclasses in
`failures.py`, so automation branches on identity while messages keep improving.

Several codes deliberately share one exit status — statuses are coarse shell signals, codes
are precise machine semantics.
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
