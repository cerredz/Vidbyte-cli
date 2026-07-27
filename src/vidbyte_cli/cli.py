"""The callable behind the `vidbyte-cli` console script.

Deliberately thin: lifecycle and the error trap live in `lib/runtime/application.py`, and
process termination lives in `__main__.py` and the generated console wrapper. `main()`
returns a status rather than calling `sys.exit`, so an embedding caller can run the CLI
without having its own process killed.
"""

from __future__ import annotations

from collections.abc import Sequence

from .lib.runtime.application import CliApplication


def main(argv: Sequence[str] | None = None) -> int:
    # Returns the status; only an executable wrapper may terminate the process.
    return CliApplication().run(argv)
