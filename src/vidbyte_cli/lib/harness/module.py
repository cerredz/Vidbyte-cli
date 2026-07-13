"""The HarnessModule protocol: the minimal contract the runtime depends on.

Both a hand-written harness (via BaseHarness) and a manifest-generated one satisfy this,
so the factory and the `harness catalog` discovery treat them identically.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import click

from .context import HarnessContext
from .types import HarnessCommandDef


@runtime_checkable
class HarnessModule(Protocol):
    # The whole surface a harness must provide. Deliberately tiny: a namespace, a
    # description, its commands, and the ability to attach itself to a parent group.
    name: str
    description: str

    def commands(self, ctx: HarnessContext) -> list[HarnessCommandDef]: ...

    def register(self, parent: click.Group, ctx: HarnessContext) -> None: ...
