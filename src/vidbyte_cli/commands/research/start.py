"""`vidbyte-cli research start <prompt>` — open a new research thread and admit its first run.

Admission returns immediately with durable identifiers rather than blocking: a research run
outlives a terminal session, and `research watch` is the explicit way to wait for one.
"""

from __future__ import annotations

import click

from ...lib.runtime.context import ApplicationContext
from .options import ResearchRunOptions
from .render import ResearchRenderer


class ResearchStartCommand:
    def register(self, parent: click.Group) -> None:
        # Options are attached before the group takes the callback, so help lists them in order.
        options = ResearchRunOptions()

        def _run(context: ApplicationContext, /, **values: object) -> None:
            self.execute(context, values)

        callback = click.argument("prompt")(click.pass_obj(_run))
        parent.command(name="start", help="Start a new research thread from a prompt")(
            options.apply(callback)
        )

    def execute(self, context: ApplicationContext, values: dict[str, object]) -> None:
        # Validates the whole request before a credential is resolved, so a malformed
        # invocation costs neither a keyring lookup nor a round trip.
        options = ResearchRunOptions()
        request = options.build(values)
        key = str(options.key(values))
        accepted = context.research_endpoints().create_run(request, key)
        rendered = ResearchRenderer().accepted(accepted, key)
        context.output().result(rendered.document, rendered.human)
