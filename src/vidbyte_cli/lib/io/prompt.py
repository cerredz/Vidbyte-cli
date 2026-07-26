"""FILE: src/vidbyte_cli/lib/io/prompt.py

PURPOSE: Resolves exactly one prompt source from a positional value, UTF-8 file, or explicit
stdin marker and applies a bounded research-compatible size policy. Interactive prompting
and product-specific request validation do not belong here.

ROLE IN CODEBASE: Research command adapters will call PromptInputResolver before application
services. IOStreams supplies injected stdin; usage_error provides stable early failures.

ARCHITECTURE NOTE: Explicit stdin (`-`) prevents commands from hanging merely because input
is redirected. Reading one extra character detects oversized content without unbounded
memory growth.

FUNCTION INVENTORY (reviewed 2026-07-26):
- PromptInputResolver(streams, max_chars) -> resolver with injected input.
- PromptInputResolver.resolve(positional, prompt_file) -> one validated prompt.

COMMON MODIFICATION PATTERNS: Change limits through constructor policy, keep all reads
bounded, and preserve source exclusivity before touching a file or stdin.

WHAT NOT TO DO IN THIS FILE:
1. Do not prompt interactively when no source is supplied.
2. Do not accept multiple sources and choose one silently.
3. Do not log or include full prompt content in errors.
4. Do not read credential tokens; lib/auth owns that path.
5. Do not interpret research filters or API request fields.

KNOWN EDGE CASES: Invalid UTF-8, directories, missing files, empty content, and content over
the limit are usage errors. A positional dash is the only stdin marker.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines exclusive prompt input and the 20,000-character bound.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
The public smoke gate verifies command startup; feature integration exercises this in PR 6.
"""

from __future__ import annotations

from pathlib import Path

from ..errors.cli_error import usage_error
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
            raise usage_error(
                "Provide exactly one prompt source.",
                "Use a positional prompt, --prompt-file PATH, or '-' for stdin.",
            )
        if positional is None and prompt_file is None:
            raise usage_error(
                "A prompt is required.",
                "Pass a positional prompt, --prompt-file PATH, or '-' for stdin.",
            )
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
            raise usage_error("The prompt file must contain valid UTF-8 text.") from error
        except (OSError, ValueError) as error:
            raise usage_error(
                f"Unable to read prompt file '{path}'.",
                "Check that the path exists and is a readable file.",
            ) from error

    def _read_stdin(self) -> str:
        # Explicit stdin remains bounded and decoding failures stay safe usage errors.
        try:
            return self._validate(self._streams.stdin.read(self._max_chars + 1))
        except UnicodeError as error:
            raise usage_error("Standard input must contain valid text.") from error

    def _validate(self, value: str) -> str:
        # Error prose reports only length, never potentially sensitive prompt content.
        if not value.strip():
            raise usage_error("The prompt must not be empty.")
        if len(value) > self._max_chars:
            raise usage_error(f"The prompt exceeds the {self._max_chars}-character limit.")
        return value
