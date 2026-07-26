"""FILE: src/vidbyte_cli/lib/output/formats.py

PURPOSE: Defines root-level presentation preferences shared by terminal detection, output
rendering, and command registration. Serialization and stream writes do not belong here.

ROLE IN CODEBASE: CliApplication parses these values, ApplicationContext stores them for one
invocation, TerminalCapabilities applies ColorMode, and OutputManager applies OutputFormat.

ARCHITECTURE NOTE: String enums make Click choices, config values, and machine-facing
diagnostics use one vocabulary without accepting arbitrary presentation modes.

FUNCTION INVENTORY (reviewed 2026-07-26):
- OutputFormat: human, single-JSON, streaming-JSONL, and suppressed result modes.
- ColorMode: automatic, requested, and disabled color preferences.

COMMON MODIFICATION PATTERNS: Add a mode only with explicit stdout/stderr semantics and
update docs/architecture.md plus every OutputManager branch.

WHAT NOT TO DO IN THIS FILE:
1. Do not inspect TTY state or environment variables.
2. Do not serialize result documents.
3. Do not define command-specific output styles.
4. Do not make enum values aliases with different behavior.

KNOWN EDGE CASES: ColorMode.ALWAYS remains subject to the security/accessibility rule that
redirected streams, TERM=dumb, and NO_COLOR disable terminal control.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines global output flags and shell-stream contracts.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises human, JSON, JSONL, and conflicting flag parsing.
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

    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"
