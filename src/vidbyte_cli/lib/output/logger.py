"""The generic harness runtime's info/warn/error calls, routed through OutputManager.

A compatibility adapter, not a design: it exists so the existing harness lifecycle keeps
working now that output policy is invocation-owned. New code calls OutputManager directly.
The process-global `logger` singleton it replaces is gone on purpose.
"""

from __future__ import annotations

from .manager import OutputManager
from .models import OutputDocument


class Logger:
    """Compatibility adapter for generic harness output."""

    def __init__(self, output: OutputManager) -> None:
        self._output = output

    def info(self, message: str) -> None:
        # A legacy presenter supplies text only, so wrap it in a stable generic record until
        # harness commands emit typed run documents.
        self._output.result(OutputDocument(kind="message", data={"message": message}), message)

    def warn(self, message: str) -> None:
        self._output.warning(message)

    def error(self, message: str) -> None:
        # A string-only legacy error carries no CliError metadata, so keep it diagnostic.
        self._output.diagnostic(message)
