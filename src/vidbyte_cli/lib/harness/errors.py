"""Maps backend failures into user-facing CliErrors, uniformly for every harness.

The classification and its agent-facing prose live in `lib/errors/failures.py`, so this
boundary only decides whether an exception was already classified. Nothing here may
stringify a backend exception: transport errors routinely quote URLs, headers, and bodies.
"""

from __future__ import annotations

from ..errors.cli_error import CliError
from ..errors.failures import HarnessInvocationFailed


def map_harness_error(error: Exception) -> CliError:
    # An already-classified failure keeps its own usage, auth, or credit semantics.
    return error if isinstance(error, CliError) else HarnessInvocationFailed(error)
