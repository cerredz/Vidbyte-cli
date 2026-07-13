"""User-facing CLI failures and the standard stub error."""

from __future__ import annotations


class CliError(Exception):
    """A user-facing CLI failure carrying the exact process exit code to terminate with.

    The central trap in vidbyte_cli.cli renders the message and exits with `exit_code`;
    any other exception is treated as an internal bug (exit 70).
    """

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def not_implemented(subject: str) -> CliError:
    # Standard stub error for scaffolded behavior that is not built yet.
    return CliError(f"{subject} is not implemented yet.", exit_code=1)
