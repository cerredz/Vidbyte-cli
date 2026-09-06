"""Validates and admits one fixed-loop local Codex persistence invocation."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import click

from ...lib.errors.failures import RuntimeAdmissionNotVerified
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Context
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...lib.runtime_primitives.persistence import PersistentCodexSession
from ...types.provider import PROVIDER_ENV_VARS, Provider
from ...types.runtime import (
    PersistenceSettings,
    PersistenceStrength,
    RuntimeAdmissionRequest,
    RuntimeGrantVerificationRequest,
    RuntimeHost,
)


class PersistenceCommand:
    """Keeps validation and provider credentials ahead of paid admission."""

    def register(self, parent: click.Group) -> None:
        # The host selector rejects unsupported execution modes before charging.
        @parent.command(name="persistence", help="Persistently drive one local Codex session")
        @click.argument("task")
        @click.option(
            "--host", type=click.Choice(("auto", "codex")), default="codex", expose_value=False
        )
        @click.option("--strength", type=click.IntRange(1, 6), default=1, show_default=True)
        @click.option(
            "--idempotency-key", "key", default=None, help="Reuse only to recover admission."
        )
        @click.pass_obj
        def _run(ctx: Context, task: str, strength: int, key: str | None) -> None:
            # Delegates without normalizing or wrapping the original task.
            self.execute(ctx, task, strength, key)

    def execute(self, context: Context, task: str, strength: int, key: str | None) -> None:
        # Resolve local prerequisites before any wallet admission, then verify before execution.
        key = key or str(uuid4())
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key) is None:
            raise click.BadParameter(
                "Use 8–128 letters, digits, dots, underscores, colons or hyphens."
            )
        plan = context.runtime_launch_planner().build(
            task, RuntimeHost.CODEX, Path.cwd(), "runtime.persistence@1"
        )
        settings = PersistenceSettings(strength=PersistenceStrength(strength))
        session = self._session(context)
        endpoints = context.runtime_endpoints()
        grant = endpoints.admit_persistence(RuntimeAdmissionRequest(host=plan.host), key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        verified = endpoints.verify_grant(
            RuntimeGrantVerificationRequest(
                grant_token=grant.grant_token,
                idempotency_key_hash=RuntimeAdmissionGate.hash_idempotency_key(key),
            )
        )
        verdict = RuntimeAdmissionGate().verify_online(plan, grant, verified)
        result = context.runtime_executor().execute_persistence(plan, settings, session, verdict)
        context.output().result(
            OutputDocument(kind="runtime.persistence", data=result.model_dump(mode="json")),
            result.text,
        )

    def _session(self, context: Context) -> PersistentCodexSession:
        # Passes only the selected BYOK key and strips known unrelated API secrets.
        credentials = context.require_provider_credentials(Provider.OPENAI)
        environment = dict(context.environment)
        for name in (
            *PROVIDER_ENV_VARS.values(),
            "GOOGLE_API_KEY",
            "VIDBYTE_API_KEY",
            "RUNTIME_ADMISSION_SIGNING_KEY",
            "CODEX_API_KEY",
        ):
            environment.pop(name, None)
        environment["OPENAI_API_KEY"] = credentials.secret_value()
        return PersistentCodexSession(environment, context.output().diagnostic)
