"""FILE: src/vidbyte_cli/lib/runtime/version.py

PURPOSE: Resolves the installed CLI distribution version from package metadata and provides
one documented source for version presentation. It prevents runtime strings from drifting
away from the built artifact. Release version changes belong in pyproject.toml, not here.

ROLE IN CODEBASE: src/vidbyte_cli/__init__.py exports the resolved value and application.py
passes it to Click. importlib.metadata is the authoritative installed-package source;
source-tree execution uses the declared development fallback.

ARCHITECTURE NOTE: This is the package metadata adapter in the runtime composition layer.
The decision is recorded in docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- VersionProvider.current() -> str: returns installed metadata or the source-tree fallback.
- current_version() -> str: public convenience query over VersionProvider.

COMMON MODIFICATION PATTERNS: Change a release version in pyproject.toml. Change the
distribution name here only as part of a coordinated package rename.

WHAT NOT TO DO IN THIS FILE:
1. Do not hardcode the release as the normal execution path; package metadata is canonical.
2. Do not make network requests to discover versions.
3. Do not compare compatibility versions; feature-specific policy owns comparison.

KNOWN EDGE CASES: Editable or raw source-tree execution can lack installed metadata. The
fallback matches pyproject.toml for predictable developer output.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
documents package-version ownership after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises --version and scripts/run_ci.py verifies installed-wheel output.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_DISTRIBUTION_NAME = "vidbyte-cli"
_SOURCE_TREE_VERSION = "0.1.0"


class VersionProvider:
    """Resolve the version attached to the installed distribution."""

    def current(self) -> str:
        # Raw source checkouts have no distribution record, so use the declared dev version.
        try:
            return version(_DISTRIBUTION_NAME)
        except PackageNotFoundError:
            return _SOURCE_TREE_VERSION


def current_version() -> str:
    # Keep callers independent from importlib.metadata and the distribution's package name.
    return VersionProvider().current()
