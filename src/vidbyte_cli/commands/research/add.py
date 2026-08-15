"""`vidbyte-cli research add <thread_id> <prompt>` — admit another run into an existing thread.

The thread ID is the public share token `research start` and `research threads` print. It is
checked locally first: the backend matches that path segment against a pattern before any
lookup, so an internal identifier pasted from another tool fails as a bare validation error
that explains nothing.
"""

from __future__ import annotations

import click

from ...lib.runtime.context import ApplicationContext
from ...types.research import ThreadId
from .options import ResearchRunOptions
from .render import ResearchRenderer


class ResearchAddCommand:
    def register(self, parent: click.Group) -> None:
        options = ResearchRunOptions()

        def _run(context: ApplicationContext, /, **values: object) -> None:
            self.execute(context, values)

        callback = click.pass_obj(_run)
        callback = click.argument("prompt")(callback)
        callback = click.argument("thread_id")(callback)
        parent.command(name="add", help="Add another prompt to an existing research thread")(
            options.apply(callback)
        )

    def execute(self, context: ApplicationContext, values: dict[str, object]) -> None:
        # The ID guard runs first so a mistyped thread never triggers a credential lookup.
        thread_id = ThreadId.parse(str(values.get("thread_id", "")))
        options = ResearchRunOptions()
        request = options.build(values)
        key = str(options.key(values))
        accepted = context.research_endpoints().append_run(str(thread_id), request, key)
        rendered = ResearchRenderer().accepted(accepted, key)
        context.output().result(rendered.document, rendered.human)
