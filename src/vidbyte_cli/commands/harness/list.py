"""`vidbyte-cli harness list` — the caller's runs, newest first.

Naming resolved (harness/list.ts:11 review comment): `list` means *your runs*; the separate
question "what harnesses are available?" is answered by `harness catalog` (catalog.py), so
one word never means two things.
"""

from __future__ import annotations

import click

from ...lib.errors.cli_error import not_implemented


class HarnessListCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="list", help="List your harness runs")
        def _run() -> None:
            self.execute()

    def execute(self) -> None:
        # Will fetch the caller's runs and render them as a summary table.
        raise not_implemented("'vidbyte-cli harness list'")
