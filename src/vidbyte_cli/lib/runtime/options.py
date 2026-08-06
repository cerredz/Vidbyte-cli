"""A service-free read of the root-option prefix, before any dynamic command can exist.

Click needs a harness namespace to exist before it dispatches, but `--format` and `--debug`
have to take effect *before* an optional harness context is built, since that context may
read credentials or fetch a manifest. So the root prefix is scanned once here, cheaply,
and Click remains the authoritative parser that renders every syntax error.

Scanning only the prefix is the point: a rewrite that searched argv for `harness` would read
`--profile harness` as a namespace and trigger remote work on a help invocation. When syntax
turns invalid after a valid machine-output prefix, that output policy is kept for Click's
structured error but attachment is refused.

An unpassed option stays `None` rather than taking a default here. These values are the
top layer of configuration precedence, and a default invented at the parser would outrank
the profile the user actually stored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ..output.formats import ColorMode, OutputFormat


@dataclass(frozen=True)
class RootOptionValues:
    """Typed root values, from either this scanner or Click's keyword callback."""

    output_format: str | None
    as_json: bool
    profile: str | None
    no_input: bool
    color: str | None
    debug: bool

    @classmethod
    def from_click(cls, values: Mapping[str, object]) -> RootOptionValues:
        # Click validates primitive types before this typed reconstruction.
        return cls(
            output_format=cast(str | None, values["output_format"]),
            as_json=cast(bool, values["as_json"]),
            profile=cast(str | None, values["profile"]),
            no_input=cast(bool, values["no_input"]),
            color=cast(str | None, values["color"]),
            debug=cast(bool, values["debug"]),
        )


@dataclass(frozen=True)
class RootInspection:
    """Validated root policy plus the untouched top-level command suffix."""

    values: RootOptionValues
    command_arguments: tuple[str, ...]
    exits_before_command: bool = False
    attach_allowed: bool = True


class RootOptionInspector:
    """One scan of one argv, holding its own cursor and accumulated root values."""

    _FLAGS = frozenset({"--json", "--no-input", "--debug"})
    _VALUED = frozenset({"--format", "--profile", "--color"})

    def __init__(self, argv: Sequence[str]) -> None:
        self._tokens = list(argv[1:])
        self._index = 0
        self._output_format: str | None = None
        self._as_json = False
        self._profile: str | None = None
        self._no_input = False
        self._color: str | None = None
        self._debug = False

    def inspect(self) -> RootInspection | None:
        # Root flags precede the command, so the first positional token ends the prefix.
        exits_before_command = False
        while self._index < len(self._tokens):
            token = self._tokens[self._index]
            if token == "--":
                self._index += 1
                break
            if not token.startswith("-"):
                break
            name, separator, inline_value = token.partition("=")
            if name in {"--help", "--version"}:
                exits_before_command = True
                break
            if not self._consume(name, separator, inline_value):
                return self._invalid()
            self._index += 1
        if not self._valid():
            return None
        suffix = tuple(self._tokens[self._index :])
        return RootInspection(self._freeze(), suffix, exits_before_command)

    def _consume(self, name: str, separator: str, inline_value: str) -> bool:
        # False means "this is not a root option Click would accept" — never a guess.
        if name in self._FLAGS:
            # Click rejects `--flag=value` for boolean flags, so this scanner must too.
            if separator:
                return False
            self._apply_flag(name)
            return True
        if name not in self._VALUED:
            return False
        value = self._read_value(separator, inline_value)
        if value is None:
            return False
        self._apply_value(name, value)
        return True

    def _read_value(self, separator: str, inline_value: str) -> str | None:
        # Both Click spellings are accepted: `--name=value` and `--name value`.
        if separator:
            return inline_value
        if self._index + 1 >= len(self._tokens):
            return None
        self._index += 1
        return self._tokens[self._index]

    def _apply_flag(self, name: str) -> None:
        if name == "--json":
            self._as_json = True
        elif name == "--no-input":
            self._no_input = True
        else:
            self._debug = True

    def _apply_value(self, name: str, value: str) -> None:
        # Normalize choice values exactly as Click's case-insensitive choices do.
        if name == "--format":
            self._output_format = value.lower()
        elif name == "--profile":
            self._profile = value
        else:
            self._color = value.lower()

    def _valid(self) -> bool:
        # An invalid choice value stays service-free and is later explained by Click.
        valid_formats = {None, *(item.value for item in OutputFormat)}
        valid_colors = {None, *(item.value for item in ColorMode)}
        return self._output_format in valid_formats and self._color in valid_colors

    def _invalid(self) -> RootInspection | None:
        # Keep an already-valid machine mode for Click's error, but never attach services.
        if not self._valid():
            return None
        return RootInspection(self._freeze(), (), attach_allowed=False)

    def _freeze(self) -> RootOptionValues:
        # Freeze before policy leaves the parser boundary.
        return RootOptionValues(
            self._output_format,
            self._as_json,
            self._profile,
            self._no_input,
            self._color,
            self._debug,
        )
