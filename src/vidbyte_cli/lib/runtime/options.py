"""FILE: src/vidbyte_cli/lib/runtime/options.py

PURPOSE: Performs the side-effect-free first pass over root CLI options before optional
dynamic command services are constructed. It returns validated presentation values and the
untouched top-level command suffix.

ROLE IN CODEBASE: CliApplication calls RootOptionInspector before harness attachment, then
reconstructs the same RootOptionValues from Click's validated callback. ApplicationContext
receives the resolved invocation policy.

ARCHITECTURE NOTE: Dynamic Click namespaces must exist before full dispatch, but root flags
must configure output and fail before credential/network work. This narrow parser mirrors
only the documented root prefix; Click remains the authoritative user-facing parser.

FUNCTION INVENTORY (reviewed 2026-07-26):
- RootOptionValues.from_click(values) -> RootOptionValues: types Click callback values.
- RootOptionInspector.inspect(argv) -> RootInspection | None: scans a valid root prefix.

COMMON MODIFICATION PATTERNS: Add a root flag to Click and this scanner in the same commit,
then add a smoke case proving its value cannot be mistaken for a command namespace.

WHAT NOT TO DO IN THIS FILE:
1. Do not invoke callbacks, commands, credential stores, config stores, or network clients.
2. Do not parse command-specific flags after the first positional top-level command.
3. Do not replace Click's error messages with custom parser prose.
4. Do not silently accept a root spelling Click rejects.
5. Do not attach a dynamic harness for root help, version, or invalid root syntax.

KNOWN EDGE CASES: Valued options support `--name value` and `--name=value`; choice values are
case-insensitive; `--` ends the root option prefix; root help/version short-circuit services.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines root-option parsing before service construction.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py covers root output modes, profile-shaped values, and conflict handling.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ..output.formats import ColorMode, OutputFormat


@dataclass(frozen=True)
class RootOptionValues:
    """Typed root values reconstructed from Click's keyword callback boundary."""

    output_format: str | None
    as_json: bool
    profile: str | None
    no_input: bool
    color: str
    debug: bool

    @classmethod
    def from_click(cls, values: Mapping[str, object]) -> RootOptionValues:
        # Click validates primitive types before this typed reconstruction.
        return cls(
            output_format=cast(str | None, values["output_format"]),
            as_json=cast(bool, values["as_json"]),
            profile=cast(str | None, values["profile"]),
            no_input=cast(bool, values["no_input"]),
            color=cast(str, values["color"]),
            debug=cast(bool, values["debug"]),
        )


@dataclass(frozen=True)
class RootInspection:
    """Validated root policy plus the untouched top-level command suffix."""

    values: RootOptionValues
    command_arguments: tuple[str, ...]
    exits_before_command: bool = False
    attach_allowed: bool = True


@dataclass
class _RootOptionState:
    """Mutable state used only while scanning the root-option prefix."""

    output_format: str | None = None
    as_json: bool = False
    profile: str | None = None
    no_input: bool = False
    color: str = ColorMode.AUTO.value
    debug: bool = False

    def freeze(self) -> RootOptionValues:
        # Freeze before policy leaves the parser boundary.
        return RootOptionValues(
            self.output_format,
            self.as_json,
            self.profile,
            self.no_input,
            self.color,
            self.debug,
        )


@dataclass(frozen=True)
class _RootToken:
    """One root option token plus its location in the original prefix."""

    tokens: Sequence[str]
    index: int
    name: str
    separator: str
    inline_value: str


class RootOptionInspector:
    """Read valid root options before optional harness services are constructed."""

    # @intent root-policy-before-dynamic-command-construction
    # Click requires dynamic commands to exist before full dispatch, but global output and
    # interaction flags must take effect before creating an optional harness context. That
    # context may eventually read credentials or fetch a manifest, so deferring root parsing
    # until Click's callback would violate help/invalid-usage side-effect guarantees.
    #
    # Keep this parser limited to the root-option prefix and let Click render every syntax
    # error. A rewrite that searches argv for "harness" can mistake values such as
    # `--profile harness` or invalid option values for a namespace and trigger remote work.
    #
    # When syntax becomes invalid after a valid machine-output prefix, preserve that output
    # policy for Click's structured error but set attach_allowed=False.
    def inspect(self, argv: Sequence[str]) -> RootInspection | None:
        # Click requires root flags before the command, so stop at the first positional token.
        tokens = list(argv[1:])
        state = _RootOptionState()
        exits_before_command = False
        index = 0
        while index < len(tokens):
            raw_token = tokens[index]
            if raw_token == "--":
                index += 1
                break
            if not raw_token.startswith("-"):
                break
            name, separator, inline_value = raw_token.partition("=")
            if name in {"--help", "--version"}:
                exits_before_command = True
                break
            token = _RootToken(tokens, index, name, separator, inline_value)
            consumed_index = self._consume(token, state)
            if consumed_index is None:
                return self._invalid_inspection(state)
            index = consumed_index + 1
        if not self._valid(state):
            return None
        return RootInspection(state.freeze(), tuple(tokens[index:]), exits_before_command)

    def _consume(self, token: _RootToken, state: _RootOptionState) -> int | None:
        # Split flag and valued-option handling so inspection stays auditable.
        if token.name in {"--json", "--no-input", "--debug"}:
            return self._consume_flag(token, state)
        if token.name not in {"--format", "--profile", "--color"}:
            return None
        read_value = self._read_value(token)
        if read_value is None:
            return None
        value, consumed_index = read_value
        self._apply_value(token.name, value, state)
        return consumed_index

    def _consume_flag(self, token: _RootToken, state: _RootOptionState) -> int | None:
        # Boolean flags reject assignment spellings that Click itself does not accept.
        if token.separator:
            return None
        state.as_json = token.name == "--json" or state.as_json
        state.no_input = token.name == "--no-input" or state.no_input
        state.debug = token.name == "--debug" or state.debug
        return token.index

    def _apply_value(self, name: str, value: str, state: _RootOptionState) -> None:
        # Normalize choice values exactly as Click's case-insensitive choices do.
        if name == "--format":
            state.output_format = value.lower()
        elif name == "--profile":
            state.profile = value
        else:
            state.color = value.lower()

    def _read_value(self, token: _RootToken) -> tuple[str, int] | None:
        # Inline and following-token Click spellings are both accepted.
        if token.separator:
            return token.inline_value, token.index
        if token.index + 1 >= len(token.tokens):
            return None
        return token.tokens[token.index + 1], token.index + 1

    def _valid(self, state: _RootOptionState) -> bool:
        # Invalid choice values stay service-free and are later explained by Click.
        valid_formats = {None, *(item.value for item in OutputFormat)}
        valid_colors = {item.value for item in ColorMode}
        return state.output_format in valid_formats and state.color in valid_colors

    def _invalid_inspection(self, state: _RootOptionState) -> RootInspection | None:
        # Preserve an already-valid machine mode for Click's error, but never attach services.
        if not self._valid(state):
            return None
        return RootInspection(state.freeze(), (), attach_allowed=False)
