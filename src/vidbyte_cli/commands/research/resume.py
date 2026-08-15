"""`vidbyte-cli research resume <run_id>` — continue a run that already settled badly.

The backend accepts a continuation only from `partial`, `failed`, or `credit_exhausted`, and
refuses every other state. That rule is enforced there rather than guessed at here: a status
read before the attempt would be a second request whose answer could already be stale.

There is no request body. A continuation replays the run's original prompt, so this command
takes no run options — passing a new prompt would silently mean starting different work.
"""

from __future__ import annotations

import click

from ...lib.runtime.context import ApplicationContext
from ...types.research import IdempotencyKey
from .render import ResearchRenderer


class ResearchResumeCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="resume", help="Continue a partial, failed, or out-of-credit run")
        @click.argument("run_id")
        @click.option(
            "--idempotency-key",
            help="Reuse a key to retry a priced mutation without being charged twice.",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, run_id: str, idempotency_key: str | None) -> None:
            self.execute(context, run_id, idempotency_key)

    def execute(self, context: ApplicationContext, run_id: str, explicit_key: str | None) -> None:
        # Validates the key before resolving credentials, then admits the continuation.
        key = str(IdempotencyKey.create(explicit_key))
        accepted = context.research_endpoints().continue_run(run_id, key)
        rendered = ResearchRenderer().accepted(accepted, key)
        context.output().result(rendered.document, rendered.human)
