"""`vidbyte-cli harness status <run_id>` — status, events, and result of one run."""

from __future__ import annotations

import click

from ...lib.errors.cli_error import not_implemented


class HarnessStatusCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="status", help="Show the status and events of a harness run")
        @click.argument("run_id")
        def _run(run_id: str) -> None:
            self.execute(run_id)

    def execute(self, run_id: str) -> None:
        # Will fetch the run from the backend and render its status block.
        raise not_implemented("'vidbyte-cli harness status'")
