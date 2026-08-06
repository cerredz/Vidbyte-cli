"""`vidbyte-cli login` — stores the user's Vidbyte API key for later commands.

There is no `--api-key` option: a secret in argv leaks into `ps`, shell history, and CI
logs. `--with-token` reads bounded stdin; anything else uses a hidden prompt.
"""

from __future__ import annotations

import click

from ...lib.auth import CredentialStorage
from ...lib.auth.input import CredentialInput
from ...lib.errors.failures import FileFallbackNotApproved
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class LoginCommand:
    def register(self, parent: click.Group) -> None:
        # Attaches `login` to the root program.
        @parent.command(name="login", help="Authenticate with a Vidbyte API key")
        @click.option(
            "--with-token",
            is_flag=True,
            help="Read the API key from stdin instead of a hidden prompt.",
        )
        @click.option(
            "--allow-file-fallback",
            is_flag=True,
            help="Approve restricted-file storage when no OS keyring is available.",
        )
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            with_token: bool,
            allow_file_fallback: bool,
        ) -> None:
            self.execute(context, with_token, allow_file_fallback)

    def execute(
        self,
        context: ApplicationContext,
        with_token: bool,
        allow_file_fallback: bool,
    ) -> None:
        config = context.resolved_config()
        credentials = CredentialInput(
            context.streams,
            context.output().terminal,
            no_input=context.options.no_input,
        ).read(from_stdin=with_token)
        # Verify-before-persist. Syntactic checks cannot prove a key authenticates, and this
        # call sits immediately before the only write so a reordering is obvious in review.
        context.credential_verifier().verify(credentials, config)
        fallback_allowed = self._fallback_consent(context, allow_file_fallback)
        # Legacy state moves only on an explicit mutation, never on a read path.
        context.migration().migrate_if_needed()
        storage = context.credential_store().write(
            credentials,
            config.profile,
            config.api_url,
            allow_file_fallback=fallback_allowed,
        )
        if storage is CredentialStorage.RESTRICTED_FILE:
            context.output().warning(
                "The API key is stored in a permission-restricted file because no OS "
                "keyring is available."
            )
        context.output().result(
            OutputDocument(
                kind="auth.login",
                data={
                    "profile": config.profile,
                    "api_url": config.api_url,
                    "storage": storage.value,
                },
            ),
            f"Authenticated profile '{config.profile}' using {storage.value}.",
        )

    def _fallback_consent(
        self,
        context: ApplicationContext,
        explicitly_allowed: bool,
    ) -> bool:
        # The fallback file is readable by anything running as this user, so consent is the
        # caller's to give — asked for here only when there is a terminal to ask on.
        if context.credential_store().keyring.available():
            return False
        if explicitly_allowed:
            return True
        if context.options.no_input or not context.output().terminal.interactive:
            raise FileFallbackNotApproved()
        return bool(
            click.confirm(
                "No OS keyring is available. Store the key in a restricted local file?",
                default=False,
                err=True,
            )
        )
