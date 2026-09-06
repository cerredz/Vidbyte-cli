"""`vidbyte-cli provider logout` — removes a stored provider key."""

from __future__ import annotations

import click

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.provider import Provider


class ProviderLogoutCommand:
    """Removes a stored BYOK provider credential."""

    def register(self, parent: click.Group) -> None:
        # Scoped logout: only the named provider for the active profile is cleared.
        @parent.command(name="logout", help="Remove a stored provider API key")
        @click.argument("provider", type=click.Choice([p.value for p in Provider]))
        @click.pass_obj
        def _run(context: ApplicationContext, provider: str) -> None:
            self.execute(context, provider)

    def execute(self, context: ApplicationContext, provider: str) -> None:
        # Clears keyring and file entries for just this provider.
        config = context.resolved_config()
        typed = Provider(provider)
        removed = context.provider_store().clear(config.profile, typed)
        context.output().result(
            OutputDocument(
                kind="provider.logout",
                data={
                    "profile": config.profile,
                    "provider": typed.value,
                    "removed": removed,
                },
            ),
            (
                f"Removed provider '{typed.value}' for profile '{config.profile}'."
                if removed
                else (
                    f"Provider '{typed.value}' was already logged out for profile "
                    f"'{config.profile}'."
                )
            ),
        )
