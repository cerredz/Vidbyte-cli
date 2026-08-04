"""`vidbyte-cli harness catalog` — the harnesses available to run.

Distinct from `harness list` (your runs). Added to resolve the naming collision flagged in
the harness/list.ts:11 review comment.
"""

from __future__ import annotations

import click

from ...lib.errors.failures import NotImplementedFeature


class HarnessCatalogCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="catalog", help="List the harnesses available to run")
        def _run() -> None:
            self.execute()

    def execute(self) -> None:
        # Will fetch the available-harness catalog and render it as an aligned table.
        raise NotImplementedFeature("'vidbyte-cli harness catalog'")
