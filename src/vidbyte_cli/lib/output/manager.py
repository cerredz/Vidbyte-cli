"""Where results, progress, warnings, and failures are allowed to go, for one invocation.

Two rules make this file worth existing. Stdout carries results only, so a shell pipeline
stays parseable while progress and diagnostics run on stderr. And a machine format never
silently degrades to human text — a consumer that asked for JSON gets JSON or an error.

Human error text repeats the agent-native description/trace/file_path that machine documents
carry, because agents shell out to the default format far more often than they pass --json.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .formats import OutputFormat
from .models import OutputDocument

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
        # Warnings stay visible in every format without corrupting structured stdout.
        self._streams.write_error(f"Warning: {message}")

    def diagnostic(self, message: str) -> None:
        # Debug and verbose details are diagnostics, never command results.
        self._streams.write_error(message)

    def error(self, error: CliError) -> None:
        # NONE suppresses ordinary output, not actionable failures.
        if self.format in {OutputFormat.JSON, OutputFormat.JSONL}:
            self._streams.write_error(self._serialize(OutputDocument.from_error(error)))
            return
        self._streams.write_error(self._human_error(error))

    def _serialize(self, document: OutputDocument) -> str:
        # Pydantic owns strict JSON encoding; failures propagate as internal software errors.
        return document.model_dump_json(exclude_none=True)

    def _human_error(self, error: CliError) -> str:
        # Text labels preserve meaning when color and cursor control are unavailable.
        lines = [
            f"Error [{error.code.value}]: {error.message}",
            f"Details: {error.description}",
            f"Trace: {error.trace}",
            f"Source: {error.file_path}",
        ]
        if error.hint is not None:
            lines.append(f"Hint: {error.hint}")
        if error.request_id is not None:
            lines.append(f"Request ID: {error.request_id}")
        return "\n".join(lines)
