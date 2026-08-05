"""FILE: src/vidbyte_cli/commands/auth/whoami.py

PURPOSE: Resolves the current scoped credential and shows its server-verified Vidbyte
identity without exposing any secret material.

ROLE IN CODEBASE: The command calls the typed AuthEndpoints through ApplicationContext and
emits one versioned result.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class WhoamiCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="whoami", help="Show the account behind the current credentials")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        identity = context.auth_endpoints().whoami()
        context.output().result(
            OutputDocument(
                kind="auth.identity",
                data={"user_id": identity.user_id, "email": identity.email},
            ),
            identity.email or identity.user_id,
        )
