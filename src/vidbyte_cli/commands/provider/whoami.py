"""`vidbyte-cli provider whoami` — shows which provider key is stored."""

from __future__ import annotations

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.provider import Provider


class ProviderWhoamiCommand:
    """Reports the identity behind a stored provider key."""

    def register(self, parent: click.Group) -> None:
        # Attaches `whoami` to the provider group.
        @parent.command(name="whoami", help="Show the provider behind stored credentials")
        @click.argument("provider", type=click.Choice([p.value for p in Provider]))
        @click.pass_obj
        def _run(context: ApplicationContext, provider: str) -> None:
            self.execute(context, provider)

    def execute(self, context: ApplicationContext, provider: str) -> None:
        # Resolves the stored provider key and re-probes to prove it is live.
        config = context.resolved_config()
        typed = Provider(provider)
        resolved = context.provider_resolver().resolve(config.profile, typed)
        if resolved is None:
            # No probe when nothing is stored — mirrors whoami's no-network rule.
            from ...lib.errors.failures import ProviderAuthenticationRequired

            raise ProviderAuthenticationRequired(typed.value)
        identity = context.provider_verifier(typed).verify(resolved.credentials)
        data: dict[str, JsonValue] = {
            "profile": config.profile,
            "provider": typed.value,
            "verified": identity.verified,
            "credential_source": resolved.source.value,
        }
        human = "\n".join(
            (
                f"Provider: {typed.value}",
                f"Verified: {identity.verified}",
                f"Profile: {config.profile}",
                f"Credential source: {resolved.source.value}",
            )
        )
        context.output().result(OutputDocument(kind="provider.whoami", data=data), human)
