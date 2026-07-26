"""FILE: src/vidbyte_cli/lib/output/logger.py

PURPOSE: Adapts the legacy harness logger interface to the invocation-owned OutputManager.
It preserves the generic info/warn/error call shape while enforcing current stream and
machine-document contracts.

ROLE IN CODEBASE: HarnessContext exposes Logger to the generic harness runtime. New command
and feature code should prefer OutputManager directly; this adapter exists until the
generic harness output lifecycle is modernized in PR 4.

ARCHITECTURE NOTE: Logger is no longer a process-global singleton. ApplicationContext builds
it around the same OutputManager used by the central error boundary.

FUNCTION INVENTORY (reviewed 2026-07-26):
- Logger.info(message) -> None: emits a generic successful result.
- Logger.warn(message) -> None: emits a stderr warning.
- Logger.error(message) -> None: emits a stderr diagnostic.

COMMON MODIFICATION PATTERNS: Keep this adapter thin. Add structured harness output by
changing harness presenters and BaseHarness rather than extending this interface.

WHAT NOT TO DO IN THIS FILE:
1. Do not call print or sys streams.
2. Do not instantiate a module-global logger.
3. Do not attach credentials, prompts, or backend diagnostics.
4. Do not implement feature-specific formatting.

KNOWN EDGE CASES: Generic info output uses kind `message`; later harness integration replaces
that fallback with typed run documents.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines invocation-owned output policy.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py validates public harness startup through this dependency graph.
"""

from __future__ import annotations

from .manager import OutputManager
from .models import OutputDocument


class Logger:
    """Compatibility adapter for generic harness output."""

    def __init__(self, output: OutputManager) -> None:
        self._output = output

    def info(self, message: str) -> None:
        # Legacy harness presenters provide only text, so wrap it in a stable generic record.
        document = OutputDocument(kind="message", data={"message": message})
        self._output.result(document, message)

    def warn(self, message: str) -> None:
        # Warnings never share the command-result stream.
        self._output.warning(message)

    def error(self, message: str) -> None:
        # A string-only legacy error has no stable CliError metadata, so keep it diagnostic.
        self._output.diagnostic(message)
