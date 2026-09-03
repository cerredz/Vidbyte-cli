"""`vidbyte-cli runtime doctor` inspects local native-agent prerequisites.

It is read-only and offline: executable paths are reported, while host configuration,
credentials, environment values, and repository contents are not inspected.
"""

from __future__ import annotations

from pathlib import Path

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class RuntimeDoctorCommand:
    """Reports the working directory and supported host availability."""

    def register(self, parent: click.Group) -> None:
        # Attaches the local-only diagnostic beneath the runtime group.
        @parent.command(name="doctor", help="Diagnose local runtime host availability")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            # Delegates command behavior to the class-owned execution method.
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Presents PATH discovery without resolving credentials or opening the network.
        statuses = context.runtime_hosts().inspect()
        working_directory = str(Path.cwd().resolve())
        rows: list[JsonValue] = [status.model_dump(mode="json") for status in statuses]
        human_rows = [
            f"{status.host.value}: {status.executable if status.available else 'not found'}"
            for status in statuses
        ]
        human = "\n".join((f"Working directory: {working_directory}", *human_rows))
        context.output().result(
            OutputDocument(
                kind="runtime.doctor", data={"working_directory": working_directory, "hosts": rows}
            ),
            human,
        )
