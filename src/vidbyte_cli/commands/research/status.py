"""`vidbyte-cli research status <run_id>` — one run's coarse durable progress.

The published status is deliberately thin: state, phase, continuation count, and a timestamp.
Live source and artifact counts are a web-product surface, not part of the API-key contract,
so nothing here estimates or invents them.

This command cannot tell a caller where to add more work. The status route carries only the
thread's internal identifier, which is rejected by path validation if it were pasted back, so
the models drop it — `research threads` is where a usable thread ID comes from.
"""

from __future__ import annotations

import click

from ...lib.runtime.context import ApplicationContext
from .render import ResearchRenderer


class ResearchStatusCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="status", help="Show one research run's current status")
        @click.argument("run_id")
        @click.pass_obj
        def _run(context: ApplicationContext, run_id: str) -> None:
            self.execute(context, run_id)

    def execute(self, context: ApplicationContext, run_id: str) -> None:
        # Reads the run once; `admitting` and `accepted` are progress, not failures.
        run = context.research_endpoints().get_run(run_id)
        rendered = ResearchRenderer().run_status(run)
        context.output().result(rendered.document, rendered.human)
