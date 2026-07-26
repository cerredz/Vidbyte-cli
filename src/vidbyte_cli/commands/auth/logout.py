"""FILE: src/vidbyte_cli/commands/auth/logout.py

PURPOSE: Idempotently removes credentials for the selected profile and API-host scope.

ROLE IN CODEBASE: This command delegates all secret storage mechanics to CredentialStore
and emits only non-secret scope metadata through OutputManager.

ARCHITECTURE NOTE: An absent credential is still a successful desired-state operation.

FUNCTION INVENTORY (reviewed 2026-07-26):
- LogoutCommand.register(parent) -> None: attaches the root command.
- LogoutCommand.execute(context) -> None: clears selected scoped credentials.

WHAT NOT TO DO IN THIS FILE:
1. Do not resolve or display the stored token.
2. Do not call keyring APIs or unlink files directly.
3. Do not treat an already-logged-out profile as a failure.
4. Do not clear credentials belonging to another profile or API host.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class LogoutCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="logout", help="Remove stored Vidbyte credentials")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        config = context.resolved_config()
        removed = context.credential_store().clear(config.profile, config.api_url)
        context.output().result(
            OutputDocument(
                kind="auth.logout",
                data={
                    "profile": config.profile,
                    "api_url": config.api_url,
                    "removed": removed,
                },
            ),
            (
                f"Removed credentials for profile '{config.profile}'."
                if removed
                else f"Profile '{config.profile}' was already logged out."
            ),
        )
