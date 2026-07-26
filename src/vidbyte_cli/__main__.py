"""FILE: src/vidbyte_cli/__main__.py

PURPOSE: Implements the `python -m vidbyte_cli` executable boundary. It converts the
reusable integer status returned by cli.main() into SystemExit and owns no other behavior.

ROLE IN CODEBASE: Python's module runner executes this file, which calls cli.py. The
installed console script targets the same main() function through packaging metadata.

ARCHITECTURE NOTE: Process termination stays at the outermost executable shell so runtime
and command code can be embedded. See docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- No exported functions or classes; module execution delegates to cli.main().

COMMON MODIFICATION PATTERNS: Keep this file unchanged when commands or runtime behavior
change. Edit it only if Python module execution requires a new outer process contract.

WHAT NOT TO DO IN THIS FILE:
1. Do not register commands; commands/__init__.py owns registration.
2. Do not render errors; lib/runtime/application.py owns rendering.
3. Do not duplicate cli.main() behavior.

KNOWN EDGE CASES: Importing this module by name does not run the guarded process exit.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines executable exit ownership after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py executes this module for every smoke invocation.
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
