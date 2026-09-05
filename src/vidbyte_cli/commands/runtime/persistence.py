"""Command shell for the local persistence runtime primitive.

The command validates host, working-directory, and strength-tier context, then reaches the
inert executor. It cannot request paid admission or spawn agents in this release.
"""

from __future__ import annotations

from pathlib import Path

import click

from ...lib.runtime.context import ApplicationContext
from ...types.runtime import PersistenceSettings, PersistenceStrength, RuntimeHost


class PersistenceCommand:
    """Builds a launch plan for the unimplemented persistence executor."""

    def register(self, parent: click.Group) -> None:
        # Attaches the persistence primitive with host and strength-tier selectors.
        @parent.command(name="persistence", help="Persistently drive a local agent session")
        @click.argument("task")
        @click.option(
            "--host",
            type=click.Choice(("auto", *(host.value for host in RuntimeHost))),
            default="auto",
            show_default=True,
        )
        @click.option(
            "--strength",
            type=click.IntRange(1, 6),
            default=1,
            show_default=True,
            help="Persistence tier from 1 (gentlest) to 6 (most insistent)",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, task: str, host: str, strength: int) -> None:
            # Delegates parsed values to the class-owned execution method.
            self.execute(context, task, host, strength)

    def execute(self, context: ApplicationContext, task: str, host: str, strength: int) -> None:
        # Builds a local plan first; the executor then fails before payment or process launch.
        requested = None if host == "auto" else RuntimeHost(host)
        plan = context.runtime_launch_planner().build(
            task, requested, Path.cwd(), "runtime.persistence@1"
        )
        settings = PersistenceSettings(strength=PersistenceStrength(strength))
        context.runtime_executor().execute_persistence(plan, settings)
