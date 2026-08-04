"""`vidbyte-cli doctor` — checks the CLI environment and credentials."""

from __future__ import annotations

import click

from ...lib.errors.failures import NotImplementedFeature


class DoctorCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="doctor", help="Diagnose CLI setup: API host, credentials, git")
        def _run() -> None:
            self.execute()

    def execute(self) -> None:
        # Will report the resolved API host, whether credentials are present and valid
        # (via /auth/whoami), and whether cwd is a usable git repo.
        raise NotImplementedFeature("'vidbyte-cli doctor'")
