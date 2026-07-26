"""FILE: src/vidbyte_cli/__init__.py

PURPOSE: Defines the intentionally small public package surface and exposes the version of
the installed distribution. Importing the package must not build commands, access
credentials, inspect repositories, or make network calls.

ROLE IN CODEBASE: Package consumers import __version__ from here; runtime/version.py
resolves the value from importlib metadata. pyproject.toml remains the release source.

ARCHITECTURE NOTE: A side-effect-free package root keeps installed-library imports distinct
from executable startup, as required by docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- __version__: installed CLI version string or source-tree development fallback.

COMMON MODIFICATION PATTERNS: Add a public export only when it is a stable package-level
contract and update src/vidbyte_cli/README.md in the same change.

WHAT NOT TO DO IN THIS FILE:
1. Do not instantiate CliApplication at import time.
2. Do not import command groups or optional feature adapters.
3. Do not hardcode a second independent release version.

KNOWN EDGE CASES: A raw source checkout may not have distribution metadata, so the version
provider supplies the value declared for source-tree development.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
explains package-version ownership after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/run_ci.py verifies the value from a built and installed wheel.
"""

from .lib.runtime.version import current_version

__version__ = current_version()

__all__ = ["__version__"]
