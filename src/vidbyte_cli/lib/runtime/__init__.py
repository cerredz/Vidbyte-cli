"""FILE: src/vidbyte_cli/lib/runtime/__init__.py

PURPOSE: Exposes version contracts that are safe during top-level package import. Heavier
composition types remain in their implementation modules so importing `vidbyte_cli` does
not load Click commands, HTTP models, or harness policy.

ROLE IN CODEBASE: src/vidbyte_cli/__init__.py reaches current_version through this package
while cli.py imports application.py explicitly. version.py provides every export here.

ARCHITECTURE NOTE: This facade is the public edge of the invocation composition layer
defined in docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- VersionProvider: installed-distribution version adapter.
- current_version() -> str: resolves the CLI version.

COMMON MODIFICATION PATTERNS: Add an export only when it is safe during `import vidbyte_cli`
and useful to multiple outside modules, then update runtime/README.md and this inventory.

WHAT NOT TO DO IN THIS FILE:
1. Do not instantiate the application or context at import time.
2. Do not re-export CliApplication or ApplicationContext eagerly; import their modules.
3. Do not hide command or optional dependency imports behind this always-loaded facade.

KNOWN EDGE CASES: This module is imported by package initialization, so it must remain free
of credential access, network work, and terminal writes.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines runtime ownership after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py validates import and startup through this facade.
"""

from .version import VersionProvider, current_version

__all__ = ["VersionProvider", "current_version"]
