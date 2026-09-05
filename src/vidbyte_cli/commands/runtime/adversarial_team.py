"""Command shell for the first local adversarial-team runtime primitive.

The command validates host and working-directory context, then reaches the inert executor.
It cannot request paid admission or spawn agents in this release.
"""

from __future__ import annotations

from pathlib import Path

import click

from ...lib.runtime.context import ApplicationContext
from ...types.runtime import RuntimeCapabilityId, RuntimeHost


class AdversarialTeamCommand:
    """Builds a launch plan for the unimplemented adversarial-team executor."""

    def register(self, parent: click.Group) -> None:
        # Attaches the first primitive with an explicit native host selector.
        @parent.command(name="adversarial-team", help="Run an adversarial agent team locally")
        @click.argument("task")
        @click.option(
            "--host",
            type=click.Choice(("auto", *(host.value for host in RuntimeHost))),
            default="auto",
            show_default=True,
        )
        @click.pass_obj
        def _run(context: ApplicationContext, task: str, host: str) -> None:
            # Delegates parsed values to the class-owned execution method.
            self.execute(context, task, host)

    def execute(self, context: ApplicationContext, task: str, host: str) -> None:
        # Builds a local plan first; the executor then fails before payment or process launch.
        requested = None if host == "auto" else RuntimeHost(host)
        plan = context.runtime_launch_planner().build(
            RuntimeCapabilityId.ADVERSARIAL_TEAM, task, requested, Path.cwd()
        )
        context.runtime_executor().execute_adversarial_team(plan)
