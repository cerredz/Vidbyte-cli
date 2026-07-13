"""Resolves a harness namespace to a HarnessModule and attaches it to the command tree.

Resolution rule (one line): prefer a hand-written module registered in
vidbyte_cli.harnesses; otherwise wrap the backend manifest in a ManifestHarness. Both
paths produce a HarnessModule, so everything downstream is identical.
"""

from __future__ import annotations

import click

from .catalog import HarnessCatalog
from .context import HarnessContext
from .manifest_harness import ManifestHarness
from .module import HarnessModule


def resolve_harness(name: str, ctx: HarnessContext) -> HarnessModule:
    # Static (hand-written) harness wins; else fall back to the manifest-generated one.
    from ...harnesses import find_static_harness

    static = find_static_harness(name)
    if static is not None:
        return static
    manifest = HarnessCatalog(ctx).load(name)
    return ManifestHarness(manifest)


def attach_harness_namespace(harness_group: click.Group, name: str, ctx: HarnessContext) -> None:
    # Builds just the requested harness's subtree under `vidbyte-cli harness`. Called from
    # the second pass in cli.py once argv has been peeked, so only the invoked harness loads.
    resolve_harness(name, ctx).register(harness_group, ctx)
