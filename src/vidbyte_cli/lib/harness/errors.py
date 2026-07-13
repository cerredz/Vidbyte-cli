"""Maps backend failures into user-facing CliErrors, uniformly for every harness."""

from __future__ import annotations

from ..errors.cli_error import CliError


def map_harness_error(error: Exception) -> CliError:
    # Turns any non-CliError raised during a harness invocation into a clean, user-facing
    # CliError. Centralized so every harness reports failures the same way and so the API
    # key can never leak into a rendered message. Real implementation will special-case the
    # ApiError envelope (code/title/detail); the stub preserves the message only.
    if isinstance(error, CliError):
        return error
    return CliError(f"Harness invocation failed: {error}")
