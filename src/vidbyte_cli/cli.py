"""FILE: src/vidbyte_cli/cli.py

PURPOSE: Provides the callable referenced by the installed console script and delegates one
invocation to the reusable runtime application. This file is the narrow bridge between
packaging and lifecycle code; command registration and failure policy do not belong here.

ROLE IN CODEBASE: pyproject.toml points `vidbyte-cli` at main(). main() creates
lib/runtime/CliApplication, whose return value is consumed by the generated console-script
wrapper or by an embedding caller. __main__.py uses the same function.

ARCHITECTURE NOTE: This thin executable shim is required by the composition-root design in
docs/design/python-cli-research-harness-program.md. Keeping sys.exit outside main() makes
the application reusable in another Python process.

FUNCTION INVENTORY (reviewed 2026-07-26):
- main(argv) -> int: runs one CLI invocation and returns its process status.

COMMON MODIFICATION PATTERNS: Change console lifecycle behavior in
lib/runtime/application.py. Change the entry point target in pyproject.toml only during a
coordinated package rename.

WHAT NOT TO DO IN THIS FILE:
1. Do not register commands; commands/__init__.py owns the static surface.
2. Do not catch or render exceptions; lib/runtime/application.py owns failure mapping.
3. Do not call sys.exit; console wrappers and __main__.py own process termination.
4. Do not construct API, auth, or config services directly.

KNOWN EDGE CASES: Embedding callers may pass argv without touching sys.argv and expect an
integer status instead of SystemExit.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines this process seam after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py invokes this path through `python -m vidbyte_cli`.
"""

from __future__ import annotations

from collections.abc import Sequence

from .lib.runtime.application import CliApplication


def main(argv: Sequence[str] | None = None) -> int:
    # Return status to the caller; only an executable wrapper may terminate the process.
    return CliApplication().run(argv)
