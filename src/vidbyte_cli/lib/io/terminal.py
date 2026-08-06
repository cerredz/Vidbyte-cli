"""What this invocation's terminal can safely be asked to do.

Capabilities are data, detected once from injected streams and an injected environment.
Injecting both is what makes redirection, CI, embedding, and Windows consoles predictable
instead of depending on process globals. No escape sequence is ever written from here.
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
        environment = os.environ if policy.environment is None else policy.environment
        terminal_allowed = cls._terminal_control_allowed(cls._is_tty(streams.stderr), environment)
        return cls(
            interactive=cls._is_tty(streams.stdin) and not policy.no_input,
            color=terminal_allowed and policy.color is not ColorMode.NEVER,
            cursor=terminal_allowed,
        )

    @staticmethod
    def _is_tty(stream: TextIO) -> bool:
        # Redirected and in-memory streams may expose no usable isatty implementation.
        isatty = getattr(stream, "isatty", None)
        if not callable(isatty):
            return False
        try:
            return bool(isatty())
        except (OSError, ValueError):
            return False

    @staticmethod
    def _terminal_control_allowed(stderr_tty: bool, environment: Mapping[str, str]) -> bool:
        # Accessibility and shell safety outrank an explicit color request: even
        # `--color always` cannot turn on control sequences here.
        if not stderr_tty:
            return False
        if environment.get("TERM", "").lower() == "dumb":
            return False
        return "NO_COLOR" not in environment
