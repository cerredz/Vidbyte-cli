"""Leveled console logger — the seam where --json / quiet modes hook in later."""

from __future__ import annotations

import sys


class Logger:
    # The only module family (with render.py) that writes to the terminal.

    def info(self, message: str) -> None:
        # Prints an informational line to stdout.
        print(message, file=sys.stdout)

    def warn(self, message: str) -> None:
        # Prints a warning line to stderr.
        print(message, file=sys.stderr)

    def error(self, message: str) -> None:
        # Prints an error line to stderr.
        print(message, file=sys.stderr)


logger = Logger()
