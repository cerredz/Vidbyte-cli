"""Exactly one prompt source per run: a positional value, a UTF-8 file, or explicit stdin.

Two rules drive the shape. Sources are exclusive and checked before anything is opened, so
an ambiguous command line can never quietly resolve one way. And stdin is read only for the
literal `-` marker, so a command whose input happens to be redirected fails fast instead of
blocking on a read that will never complete.

Reads take one character past the limit: that detects oversized input without pulling an
arbitrarily large file into memory. Error prose reports lengths, never prompt content.
"""

from __future__ import annotations

from pathlib import Path

from ..errors.failures import (
    AmbiguousPromptSource,
    EmptyPrompt,
    MissingPrompt,
    PromptFileNotUtf8,
    PromptFileUnreadable,
    PromptTooLong,
    StandardInputNotText,
)
from .streams import IOStreams

_DEFAULT_MAX_CHARS = 20_000


class PromptInputResolver:
    """Bounded resolver for explicit text, file, or stdin prompt input."""

    def __init__(self, streams: IOStreams, max_chars: int = _DEFAULT_MAX_CHARS) -> None:
        self._streams = streams
        self._max_chars = max_chars

    def resolve(self, positional: str | None, prompt_file: str | None) -> str:
        # Reject ambiguity before reading either external source.
        if positional is not None and prompt_file is not None:
            raise AmbiguousPromptSource()
        if positional is None and prompt_file is None:
            raise MissingPrompt()
        if prompt_file is not None:
            return self._read_file(Path(prompt_file))
        if positional == "-":
            return self._read_stdin()
        return self._validate(positional or "")

    def _read_file(self, path: Path) -> str:
        # UTF-8 is explicit so machine behavior does not depend on the host locale.
        try:
            with path.open("r", encoding="utf-8") as handle:
                return self._validate(handle.read(self._max_chars + 1))
        except UnicodeDecodeError as error:
            raise PromptFileNotUtf8(error) from error
        except (OSError, ValueError) as error:
            raise PromptFileUnreadable(str(path), error) from error

    def _read_stdin(self) -> str:
        # Explicit stdin remains bounded and decoding failures stay safe usage errors.
        try:
            return self._validate(self._streams.stdin.read(self._max_chars + 1))
        except UnicodeError as error:
            raise StandardInputNotText(error) from error

    def _validate(self, value: str) -> str:
        if not value.strip():
            raise EmptyPrompt()
        if len(value) > self._max_chars:
            raise PromptTooLong(self._max_chars)
        return value
