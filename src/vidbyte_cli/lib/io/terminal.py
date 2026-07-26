"""FILE: src/vidbyte_cli/lib/io/terminal.py

PURPOSE: Detects interaction, color, and cursor capabilities for one invocation from
injected streams plus an injected environment. Rendering policy and ANSI generation do not
belong here.

ROLE IN CODEBASE: ApplicationContext detects TerminalCapabilities after root flags parse.
OutputManager uses the immutable result to avoid terminal control on redirected streams.
Prompt readers use interactive to decide whether prompting is permitted.

ARCHITECTURE NOTE: Capability detection is data, not process-global behavior. Injection
makes embedding, redirection, CI, and Windows consoles predictable.

FUNCTION INVENTORY (reviewed 2026-07-26):
- TerminalPolicy: immutable color, interaction, and environment preferences.
- TerminalCapabilities.detect(streams, policy) -> capabilities.

COMMON MODIFICATION PATTERNS: Add a capability only when all platform checks can be made
without writing to the terminal, then update output policy and this header.

WHAT NOT TO DO IN THIS FILE:
1. Do not write terminal escape sequences.
2. Do not prompt or read stdin content.
3. Do not override NO_COLOR or TERM=dumb.
4. Do not assume an injected TextIO implements isatty().

KNOWN EDGE CASES: Broken or in-memory streams may lack a usable isatty method. A requested
always-color mode still cannot enable control sequences on a non-TTY under the CLI contract.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines accessibility and noninteractive behavior.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py runs redirected subprocesses, exercising the non-TTY path.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TextIO

from ..output.formats import ColorMode
from .streams import IOStreams


@dataclass(frozen=True)
class TerminalPolicy:
    """Preferences and environment used for one capability decision."""

    color: ColorMode = ColorMode.AUTO
    no_input: bool = False
    environment: Mapping[str, str] | None = None


@dataclass(frozen=True)
class TerminalCapabilities:
    """Terminal features safe to use for one invocation."""

    interactive: bool
    color: bool
    cursor: bool

    @classmethod
    def detect(cls, streams: IOStreams, policy: TerminalPolicy) -> TerminalCapabilities:
        # Environment injection avoids hiding global reads inside renderers.
        resolved_environment = os.environ if policy.environment is None else policy.environment
        stdin_tty = _is_tty(streams.stdin)
        stderr_tty = _is_tty(streams.stderr)
        terminal_allowed = _terminal_control_allowed(stderr_tty, resolved_environment)
        return cls(
            interactive=stdin_tty and not policy.no_input,
            color=terminal_allowed and policy.color is not ColorMode.NEVER,
            cursor=terminal_allowed,
        )


def _is_tty(stream: TextIO) -> bool:
    # Some redirected and in-memory streams expose no usable isatty implementation.
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except (OSError, ValueError):
        return False


def _terminal_control_allowed(stderr_tty: bool, environment: Mapping[str, str]) -> bool:
    # Accessibility and shell safety take precedence over an explicit color preference.
    if not stderr_tty:
        return False
    if environment.get("TERM", "").lower() == "dumb":
        return False
    return "NO_COLOR" not in environment
