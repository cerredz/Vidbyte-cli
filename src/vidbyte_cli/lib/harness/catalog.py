"""Fetches and caches harness manifests.

The only networked part of the harness runtime. Manifests are cached under
~/.vidbyte/manifests so `--help` works offline and the two-pass namespace peek in cli.py
avoids a round-trip when a manifest is already cached. Version-skew is enforced here: a
manifest that needs a newer CLI fails loudly rather than dropping unknown flags.
"""

from __future__ import annotations

from ...types.manifest import HarnessManifest
from ..errors.failures import NotImplementedFeature
from .context import HarnessContext


class HarnessCatalog:
    def __init__(self, ctx: HarnessContext) -> None:
        self._ctx = ctx

    def load(self, name: str) -> HarnessManifest:
        # Returns a harness manifest, cache-first with a network fallback, then checks that
        # the installed CLI satisfies manifest.min_cli_version.
        raise NotImplementedFeature("harness manifest loading")

    def refresh(self, name: str) -> HarnessManifest:
        # Forces a network fetch and rewrites the cache entry.
        raise NotImplementedFeature("harness manifest refresh")
