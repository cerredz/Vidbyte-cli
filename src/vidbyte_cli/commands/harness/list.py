"""FILE: src/vidbyte_cli/commands/harness/list.py

PURPOSE: Lists the caller's generic harness runs through a typed endpoint.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class HarnessListCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="list", help="List your harness runs")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        runs = context.harness_endpoints().list_runs()
        context.output().result(
            OutputDocument(
                kind="harness.run.list",
                data={
                    "runs": [
                        {
                            "run_id": run.run_id,
                            "harness": run.harness,
                            "command": run.command,
                            "status": run.status,
                        }
                        for run in runs
                    ]
                },
            ),
            context.harness_context().render.render_list(runs),
        )
