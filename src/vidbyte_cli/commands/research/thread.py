"""`vidbyte-cli research thread <thread_id>` — one research thread and its rollup counters.

Reads the same thread the portfolio lists, plus the latest run's phase and the favourite flag
a portfolio row omits. A soft-deleted thread reads as not found, the same as one that never
existed, because reads are scoped to the caller.
"""

from __future__ import annotations

import click

from ...lib.runtime.context import ApplicationContext
from ...types.research import ThreadId
from .render import ResearchRenderer


class ResearchThreadCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="thread", help="Show one research thread")
        @click.argument("thread_id")
        @click.pass_obj
        def _run(context: ApplicationContext, thread_id: str) -> None:
            self.execute(context, thread_id)

    def execute(self, context: ApplicationContext, thread_id: str) -> None:
        # The ID guard runs first so a mistyped thread never triggers a credential lookup.
        parsed = ThreadId.parse(thread_id)
        thread = context.research_endpoints().get_thread(str(parsed))
        rendered = ResearchRenderer().thread(thread)
        context.output().result(rendered.document, rendered.human)
