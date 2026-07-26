"""FILE: src/vidbyte_cli/lib/output/manager.py

PURPOSE: Enforces the CLI's stdout/stderr and human/machine presentation contracts for one
invocation. Feature presenters create documents and human summaries; physical streams and
format selection are centralized here.

ROLE IN CODEBASE: ApplicationContext owns one OutputManager. Commands, log adapters, and the
ErrorHandler use it for results, transitions, warnings, diagnostics, and safe errors.

ARCHITECTURE NOTE: Result records alone use stdout. Human progress and all diagnostics use
stderr. JSON mode emits one result document, while JSONL may stream transition records.

FUNCTION INVENTORY (reviewed 2026-07-26):
- OutputStreams: structural stream-write contract that avoids concrete IO coupling.
- OutputPolicy: immutable format and terminal-capability inputs.
- OutputManager.result(document, human) -> None: emits one successful command result.
- OutputManager.transition(document, human) -> None: emits coarse progress when permitted.
- OutputManager.warning(message) -> None: writes a labeled warning to stderr.
- OutputManager.diagnostic(message) -> None: writes an explicit diagnostic to stderr.
- OutputManager.error(error) -> None: emits a safe human or structured error to stderr.

COMMON MODIFICATION PATTERNS: Add a new channel behavior here, document its shell contract,
and keep feature-specific formatting in its presenter.

WHAT NOT TO DO IN THIS FILE:
1. Do not call print or process-global sys streams.
2. Do not place progress or errors on stdout.
3. Do not silently fall back to human text after serialization fails.
4. Do not serialize CliError.cause.
5. Do not add feature-specific tables or artifact formatting.

KNOWN EDGE CASES: NONE suppresses results and transitions but retains errors. Broken pipes
propagate to ErrorHandler, which treats downstream consumer closure as successful.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines the stdout/stderr, JSON, and JSONL guarantees.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py validates representative public output modes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .formats import OutputFormat
from .models import OutputDocument, error_document

if TYPE_CHECKING:
    from ..errors.cli_error import CliError
    from ..io.terminal import TerminalCapabilities


class OutputStreams(Protocol):
    """Minimum physical stream behavior required by output policy."""

    def write_output(self, message: str) -> None: ...

    def write_error(self, message: str) -> None: ...


@dataclass(frozen=True)
class OutputPolicy:
    """Presentation choices used by one output manager."""

    output_format: OutputFormat
    terminal: TerminalCapabilities


class OutputManager:
    """Invocation-owned presentation and stream policy."""

    def __init__(self, streams: OutputStreams, policy: OutputPolicy) -> None:
        self._streams = streams
        self.format = policy.output_format
        self.terminal = policy.terminal

    def result(self, document: OutputDocument, human: str) -> None:
        # JSON and JSONL both emit one record here; only JSONL may emit earlier transitions.
        if self.format is OutputFormat.NONE:
            return
        if self.format is OutputFormat.HUMAN:
            self._streams.write_output(human)
            return
        self._streams.write_output(self._serialize(document))

    def transition(self, document: OutputDocument, human: str) -> None:
        # A single-JSON consumer must see exactly one final stdout document.
        if self.format is OutputFormat.JSONL:
            self._streams.write_output(self._serialize(document))
        elif self.format is OutputFormat.HUMAN:
            self._streams.write_error(human)

    def warning(self, message: str) -> None:
        # Warnings remain visible in every format without corrupting structured stdout.
        self._streams.write_error(f"Warning: {message}")

    def diagnostic(self, message: str) -> None:
        # Debug and verbose details are explicitly diagnostic and never command results.
        self._streams.write_error(message)

    def error(self, error: CliError) -> None:
        # NONE suppresses ordinary output, not actionable failures.
        if self.format in {OutputFormat.JSON, OutputFormat.JSONL}:
            self._streams.write_error(self._serialize(error_document(error)))
            return
        self._streams.write_error(self._human_error(error))

    def _serialize(self, document: OutputDocument) -> str:
        # Pydantic owns strict JSON encoding; failures propagate as internal software errors.
        return document.model_dump_json(exclude_none=True)

    def _human_error(self, error: CliError) -> str:
        # Text labels preserve meaning when color and cursor control are unavailable.
        lines = [f"Error [{error.code.value}]: {error.message}"]
        if error.hint is not None:
            lines.append(f"Hint: {error.hint}")
        if error.request_id is not None:
            lines.append(f"Request ID: {error.request_id}")
        return "\n".join(lines)
