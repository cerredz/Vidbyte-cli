"""One source for the CLI's version: the installed distribution's own metadata.

pyproject.toml stays the release source of truth; nothing here duplicates the release
number. A raw source checkout has no distribution record, so it reports a dev marker rather
than impersonating a release.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_DISTRIBUTION_NAME = "vidbyte-cli"
# Deliberately not "0.1.0": a source tree must not claim to be the released version.
_SOURCE_TREE_VERSION = "0.1.0.dev0"


class VersionProvider:
    """Resolves the version of the installed distribution."""

    def current(self) -> str:
        # Editable/source execution has no metadata; fall back rather than raise.
        try:
            return version(_DISTRIBUTION_NAME)
        except PackageNotFoundError:
            return _SOURCE_TREE_VERSION


def current_version() -> str:
    # Keeps callers independent of importlib.metadata and the distribution name.
    return VersionProvider().current()
