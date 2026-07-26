"""FILE: src/vidbyte_cli/commands/auth/login.py

PURPOSE: Implements explicit, hidden-input Vidbyte login with server verification before
durable storage and explicit consent when only a restricted-file fallback is available.

ROLE IN CODEBASE: This thin adapter coordinates CredentialInput, CredentialVerifier,
StateMigration, CredentialStore, and OutputManager through ApplicationContext.

ARCHITECTURE NOTE: There is deliberately no raw token option and no environment-to-store
path. `--with-token` means bounded stdin; normal interactive entry is hidden.

FUNCTION INVENTORY (reviewed 2026-07-26):
- LoginCommand.register(parent) -> None: attaches options and the Click adapter.
- LoginCommand.execute(context, with_token, allow_file_fallback) -> None: runs login.

WHAT NOT TO DO IN THIS FILE:
1. Do not accept or echo a token in argv.
2. Do not store before CredentialVerifier succeeds.
3. Do not persist VIDBYTE_API_KEY implicitly.
4. Do not call HTTP directly; the injected verifier owns that boundary.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import click

from ...lib.auth import CredentialStorage
from ...lib.auth.input import CredentialInput
from ...lib.errors import usage_error
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class LoginCommand:
    """Authenticate one selected profile/API-host scope."""

    def register(self, parent: click.Group) -> None:
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
        # @intent verified-credentials-only-cross-persistence-boundary
        # Syntactic token checks cannot prove authentication. Keeping this call immediately
        # before mutation makes an accidental store-before-verify rewrite easy to review.
        context.credential_verifier().verify(credentials, config)
        store = context.credential_store()
        fallback_allowed = self._fallback_consent(context, allow_file_fallback)
        context.migration().migrate_if_needed()
        storage = store.write(
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
        if context.credential_store().keyring.available():
            return False
        if explicitly_allowed:
            return True
        if context.options.no_input or not context.output().terminal.interactive:
            raise usage_error(
                "No OS keyring is available and file storage was not approved.",
                "Retry with --allow-file-fallback after reviewing the storage warning.",
            )
        return bool(
            click.confirm(
                "No OS keyring is available. Store the key in a restricted local file?",
                default=False,
                err=True,
            )
        )
