"""FILE: src/vidbyte_cli/commands/setup/doctor.py

PURPOSE: Reports safe, read-only facts about local configuration, credentials, repository,
and API identity reachability without failing the entire diagnostic at the first problem.

ROLE IN CODEBASE: The command composes typed local, Git, and API boundaries into one result.

ARCHITECTURE NOTE: The result contains credential presence/source, never credential value.
Doctor does not migrate or repair state because diagnosis is a read-only request.

FUNCTION INVENTORY (reviewed 2026-07-26):
- DoctorCommand.register(parent) -> None: attaches the root command.
- DoctorCommand.execute(context) -> None: collects and emits safe local diagnostics.

WHAT NOT TO DO IN THIS FILE:
1. Do not render or inspect token contents.
2. Do not migrate, repair, or write local state.
3. Do not call network routes until PR 4's API diagnostic is integrated.
4. Do not include keyring backend exception strings.

TESTS: No feature tests are added under the approved no-tests workflow. scripts/smoke.py
executes doctor in human and machine modes.
"""

from __future__ import annotations

import click
from pydantic import JsonValue

from ...lib.errors import CliError
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class DoctorCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="doctor", help="Diagnose local CLI configuration and credentials")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        config = context.resolved_config()
        store = context.credential_store()
        credential = context.credential_resolver().resolve(config.profile, config.api_url)
        paths = context.paths()
        git_status = self._git_status(context)
        api_status = self._api_status(context, credential is not None)
        data: dict[str, JsonValue] = {
            "profile": config.profile,
            "api_url": config.api_url,
            "config_path": config.config_path,
            "credential_present": credential is not None,
            "credential_source": credential.source.value if credential is not None else None,
            "keyring_available": store.keyring.available(),
            "legacy_state_present": paths.legacy_root.exists(),
            "git": git_status,
            "api": api_status,
        }
        credential_status = (
            f"present ({credential.source.value})" if credential is not None else "not found"
        )
        human = "\n".join(
            (
                f"Profile: {config.profile}",
                f"API URL: {config.api_url}",
                f"Credentials: {credential_status}",
                f"OS keyring: {'available' if data['keyring_available'] else 'unavailable'}",
                f"Legacy state: {'present' if data['legacy_state_present'] else 'not found'}",
                f"Git: {git_status}",
                f"API: {api_status}",
            )
        )
        context.output().result(OutputDocument(kind="doctor.local", data=data), human)

    def _git_status(self, context: ApplicationContext) -> str:
        try:
            repository = context.harness_context().repo.inspect()
        except CliError:
            return "unavailable"
        return "dirty" if repository.is_dirty else "clean"

    def _api_status(self, context: ApplicationContext, has_credential: bool) -> str:
        if not has_credential:
            return "not_checked_no_credentials"
        try:
            context.auth_endpoints().whoami()
        except CliError as error:
            return error.code.value.lower()
        return "reachable"
