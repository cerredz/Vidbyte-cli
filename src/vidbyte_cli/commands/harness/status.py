"""FILE: src/vidbyte_cli/commands/harness/status.py

PURPOSE: Fetches and renders one generic harness run snapshot.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class HarnessStatusCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="status", help="Show the status and events of a harness run")
        @click.argument("run_id")
        @click.pass_obj
        def _run(context: ApplicationContext, run_id: str) -> None:
            self.execute(context, run_id)

    def execute(self, context: ApplicationContext, run_id: str) -> None:
        run = context.harness_endpoints().get_run(run_id)
        context.output().result(
            OutputDocument(
                kind="harness.run",
                data={
                    "run_id": run.run_id,
                    "harness": run.harness,
                    "command": run.command,
                    "status": run.status,
                    "created_at": run.created_at,
                    "updated_at": run.updated_at,
                },
            ),
            context.harness_context().render.render_status(run),
        )
