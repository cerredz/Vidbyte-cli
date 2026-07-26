"""FILE: scripts/smoke.py

PURPOSE: Verifies that the public CLI module boots and representative static plus harness
help screens render without credentials or network access. This script is a fast startup
gate, not a substitute for feature tests or live API validation.

ROLE IN CODEBASE: scripts/run_ci.py invokes SmokeRunner after lint, typing, and compilation.
Each case launches `python -m vidbyte_cli`, exercising __main__.py, cli.py, runtime
composition, command registration, and the static software-engineering harness.

ARCHITECTURE NOTE: The approved no-tests workflow retains and strengthens deterministic
smoke verification. The rationale is in docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- SmokeRunner.run() -> int: launches every declared invocation and reports the first failure.
- main() -> int: constructs and runs the smoke verifier.

COMMON MODIFICATION PATTERNS: Add a help or version invocation when the public command tree
gains a stable group. Keep cases credential-free and avoid live API operations.

WHAT NOT TO DO IN THIS FILE:
1. Do not call real Vidbyte routes or require API keys.
2. Do not mutate user config, credentials, repositories, or backend state.
3. Do not treat startup smoke coverage as feature correctness.
4. Do not bypass the public `python -m vidbyte_cli` entry point.

KNOWN EDGE CASES: Subprocess output is captured so a failed case can print the exact stderr.
The source package must be installed or made importable by the invoking environment.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines verification scope after this stack merges.

TESTS: This file is itself the approved offline smoke verification and is executed by
scripts/run_ci.py on every supported CI platform.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

_CompletedCommand = subprocess.CompletedProcess[str]

_INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("--help",),
    ("--version",),
    ("harness", "--help"),
    ("harness", "software-engineering", "--help"),
    ("harness", "software-engineering", "fix", "--help"),
    ("connect", "--help"),
    ("config", "--help"),
)


class SmokeRunner:
    """Launch representative commands through the public module entry point."""

    def run(self) -> int:
        # Stop at the first broken public invocation and preserve its diagnostic output.
        for arguments in _INVOCATIONS:
            result = self._invoke(arguments)
            if result.returncode != 0:
                self._report_failure(arguments, result)
                return 1
            self._report_success(arguments)
        sys.stdout.write("smoke passed\n")
        return 0

    def _invoke(self, arguments: Sequence[str]) -> _CompletedCommand:
        # Launch a fresh process so import and executable-boundary failures remain visible.
        return subprocess.run(
            [sys.executable, "-m", "vidbyte_cli", *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def _report_failure(self, arguments: Sequence[str], result: _CompletedCommand) -> None:
        # CI needs the exact invocation and stderr to route a startup failure quickly.
        sys.stderr.write(f"FAIL: {' '.join(arguments)} (exit {result.returncode})\n")
        sys.stderr.write(result.stderr)

    def _report_success(self, arguments: Sequence[str]) -> None:
        # One compact line per case makes cross-platform CI progress easy to scan.
        sys.stdout.write(f"ok: vidbyte-cli {' '.join(arguments)}\n")


def main() -> int:
    # Keep the executable wrapper small so SmokeRunner is reusable from the CI orchestrator.
    return SmokeRunner().run()


if __name__ == "__main__":
    raise SystemExit(main())
