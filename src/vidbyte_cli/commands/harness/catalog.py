"""FILE: src/vidbyte_cli/commands/harness/catalog.py

PURPOSE: Lists generic harnesses available to the current account.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class HarnessCatalogCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="catalog", help="List the harnesses available to run")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        harnesses = context.harness_endpoints().list_catalog()
        context.output().result(
            OutputDocument(
                kind="harness.catalog",
                data={
                    "harnesses": [
                        {
                            "name": item.name,
                            "version": item.version,
                            "description": item.description,
                        }
                        for item in harnesses
                    ]
                },
            ),
            context.harness_context().render.render_catalog(harnesses),
        )
