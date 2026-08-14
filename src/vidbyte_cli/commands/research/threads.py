"""`vidbyte-cli research threads` — one page of the caller's research threads.

This and `research start` are the only two places a usable thread ID is minted, which is why
every row leads with it. Paging is cursor-based: an absent `next_cursor` is the end of the
collection, and the command never loops on the caller's behalf.
"""

from __future__ import annotations

import click

from ...lib.runtime.context import ApplicationContext
from .render import ResearchRenderer

_MAXIMUM_PAGE_SIZE = 100


class ResearchThreadsCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="threads", help="List your research threads")
        @click.option("--cursor", help="Continue from the cursor a previous page reported.")
        @click.option(
            "--limit",
            type=click.IntRange(1, _MAXIMUM_PAGE_SIZE),
            help="How many threads to return. The server picks a default when unset.",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, cursor: str | None, limit: int | None) -> None:
            self.execute(context, cursor, limit)

    def execute(self, context: ApplicationContext, cursor: str | None, limit: int | None) -> None:
        # Reads exactly one page; the cursor is opaque and is echoed back, never parsed.
        page = context.research_endpoints().get_portfolio(cursor, limit)
        rendered = ResearchRenderer().thread_page(page)
        context.output().result(rendered.document, rendered.human)
