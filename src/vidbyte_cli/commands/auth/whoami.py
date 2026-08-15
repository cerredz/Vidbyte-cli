"""`vidbyte-cli whoami` — shows which account the stored credentials belong to.

The identity comes from the same backend check login uses, so the two commands can never
disagree about whether a key is good. Reading is done through `CredentialResolver`, which puts
`VIDBYTE_API_KEY` ahead of the keyring — correct here, because that is the key later commands
would actually send.
"""

from __future__ import annotations

import click
from pydantic import JsonValue

from ...lib.errors.failures import AuthenticationRequired
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class WhoamiCommand:
    def register(self, parent: click.Group) -> None:
        # Attaches `whoami` to the root program.
        @parent.command(name="whoami", help="Show the account behind the stored credentials")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Resolves the stored credential, proves it against the backend, and prints the identity.
        config = context.resolved_config()
        credential = context.credential_resolver().resolve(config.profile, config.api_url)
        if credential is None:
            # Raised before any request, so an unauthenticated machine never reaches the network.
            raise AuthenticationRequired()
        identity = context.credential_verifier().verify(credential.credentials, config)
        data: dict[str, JsonValue] = {
            "profile": config.profile,
            "api_url": config.api_url,
            "username": identity.username,
            "account_tier": identity.account_tier,
            "credential_source": credential.source.value,
        }
        human = "\n".join(
            (
                f"Authenticated as: {identity.username}",
                f"Account tier: {identity.account_tier}",
                f"Profile: {config.profile}",
                f"API URL: {config.api_url}",
                f"Credential source: {credential.source.value}",
            )
        )
        context.output().result(OutputDocument(kind="auth.whoami", data=data), human)
