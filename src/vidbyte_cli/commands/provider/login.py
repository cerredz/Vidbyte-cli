"""`vidbyte-cli provider login` — verifies a provider key then stores it."""

from __future__ import annotations

import click

from ...lib.auth.provider_input import ProviderCredentialInput
from ...lib.errors.failures import FileFallbackNotApprovedForProvider
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.provider import Provider


class ProviderLoginCommand:
    """Authenticates a BYOK provider key."""

    def register(self, parent: click.Group) -> None:
        # Adds `provider login <provider>` with optional stdin and fallback flags.
        @parent.command(
            name="login",
            help="Authenticate a provider API key (openai, claude, grok, deepseek, glm, muse)",
        )
        @click.argument("provider", type=click.Choice([p.value for p in Provider]))
        @click.option(
            "--with-token",
            is_flag=True,
            help="Read the provider key from stdin instead of a hidden prompt.",
        )
        @click.option(
            "--allow-file-fallback",
            is_flag=True,
            help="Approve restricted-file storage when no OS keyring is available.",
        )
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            provider: str,
            with_token: bool,
            allow_file_fallback: bool,
        ) -> None:
            self.execute(context, provider, with_token, allow_file_fallback)

    def execute(
        self,
        context: ApplicationContext,
        provider: str,
        with_token: bool,
        allow_file_fallback: bool,
    ) -> None:
        # Verify-before-persist so a bad key never reaches storage.
        config = context.resolved_config()
        typed = Provider(provider)
        credentials = ProviderCredentialInput(
            context.streams,
            context.output().terminal,
            no_input=context.options.no_input,
            provider=typed,
        ).read(from_stdin=with_token)
        context.provider_verifier(typed).verify(credentials)
        fallback_allowed = self._fallback_consent(context, allow_file_fallback)
        context.migration().migrate_if_needed()
        storage = context.provider_store().write(
            credentials,
            config.profile,
            typed,
            allow_file_fallback=fallback_allowed,
        )
        if storage.value == "restricted_file":
            context.output().warning(
                "The provider key is stored in a permission-restricted file because no OS "
                "keyring is available."
            )
        context.output().result(
            OutputDocument(
                kind="provider.login",
                data={
                    "profile": config.profile,
                    "provider": typed.value,
                    "storage": storage.value,
                },
            ),
            (
                f"Authenticated provider '{typed.value}' for profile "
                f"'{config.profile}' using {storage.value}."
            ),
        )

    def _fallback_consent(self, context: ApplicationContext, explicitly_allowed: bool) -> bool:
        # Restricted file needs explicit consent when no keyring is available.
        if context.provider_store().keyring.available():
            return False
        if explicitly_allowed:
            return True
        if context.options.no_input or not context.output().terminal.interactive:
            raise FileFallbackNotApprovedForProvider(typed_name="provider")
        return bool(
            click.confirm(
                "No OS keyring is available. Store the provider key in a restricted local file?",
                default=False,
                err=True,
            )
        )
