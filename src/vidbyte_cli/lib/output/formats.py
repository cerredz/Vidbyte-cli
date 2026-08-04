"""The root presentation vocabulary shared by flags, terminal detection, and rendering.

String enums keep Click choices, config values, and diagnostics on one set of spellings.
Nothing here inspects a TTY or serializes a document — `lib/io` owns capability detection
and `manager.py` owns stream policy.
"""

from __future__ import annotations

from enum import StrEnum


class OutputFormat(StrEnum):
    """Supported result serialization modes."""

    HUMAN = "human"
    JSON = "json"
    JSONL = "jsonl"
    NONE = "none"


class ColorMode(StrEnum):
    """User preference for terminal color when the stream permits it."""

    # ALWAYS is still subject to the accessibility rule: a redirected stream, TERM=dumb, or
    # NO_COLOR disables terminal control regardless of what was requested.
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"
