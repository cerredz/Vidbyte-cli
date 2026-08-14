"""`vidbyte-cli doctor` — checks the CLI environment and credentials.

Diagnosis is read-only: doctor never migrates or repairs, because a user running it to find
out what is wrong should not have the answer change underneath them. It reports whether a
credential exists and where it came from, never its value. API identity and repository
checks arrive with the HTTP platform.
"""

from __future__ import annotations

import click
from pydantic import JsonValue

from ...lib.auth.credentials import Credentials
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
        keyring_available = store.keyring.available()
        legacy_present = context.paths().legacy_root.exists()
        # A credential written by hand rather than by login never crossed the input guard, so
        # the format is reported: the backend ignores a non-live key, which otherwise looks
        # exactly like being logged out.
        live_format = (
            Credentials.is_live_format(credential.credentials.secret_value())
            if credential is not None
            else None
        )
        data: dict[str, JsonValue] = {
            "profile": config.profile,
            "api_url": config.api_url,
            "config_path": config.config_path,
            "credential_present": credential is not None,
            "credential_source": credential.source.value if credential is not None else None,
            "credential_live_format": live_format,
            "keyring_available": keyring_available,
            "legacy_state_present": legacy_present,
        }
        credential_status = (
            f"present ({credential.source.value})" if credential is not None else "not found"
        )
        if live_format is False:
            credential_status += " - not a live key, the backend will ignore it"
        human = "\n".join(
            (
                f"Profile: {config.profile}",
                f"API URL: {config.api_url}",
                f"Credentials: {credential_status}",
                f"OS keyring: {'available' if keyring_available else 'unavailable'}",
                f"Legacy state: {'present' if legacy_present else 'not found'}",
            )
        )
        context.output().result(OutputDocument(kind="doctor.local", data=data), human)
