"""Resolves a harness namespace to a HarnessModule from its two possible sources.

Replaces the old free-function factory (resolve_harness + find_static_harness + an ad-hoc
inline HarnessCatalog) with a single collaborator that owns both sources, matching the DI
style the rest of the codebase already uses with HarnessContext (resolves the factory.py:32
review comment).

Resolution rule (one line): a hand-written module registered in vidbyte_cli.harnesses wins;
otherwise wrap the backend manifest in a ManifestHarness. Both paths produce a HarnessModule,
so everything downstream is identical.
"""

from __future__ import annotations

import click

from .catalog import HarnessCatalog
from .context import HarnessContext
from .manifest_harness import ManifestHarness
from .module import HarnessModule


class HarnessRegistry:
    def __init__(self, static: dict[str, HarnessModule], catalog: HarnessCatalog) -> None:
        # `static` maps namespace -> hand-written module; `catalog` supplies manifests for
        # everything else. Injecting both keeps resolution testable and free of import-time
        # coupling to the harnesses package.
        self._static = static
        self._catalog = catalog

    def resolve(self, name: str) -> HarnessModule:
        # Static (hand-written) harness wins; else fall back to the manifest-generated one.
        if name in self._static:
            return self._static[name]
        return ManifestHarness(self._catalog.load(name))

    def attach(self, harness_group: click.Group, name: str, ctx: HarnessContext) -> None:
        # Builds just the requested harness's subtree under `vidbyte-cli harness`. Called from
        # the second pass in cli.py once argv has been peeked, so only the invoked harness
        # loads.
        self.resolve(name).register(harness_group, ctx)
