"""Validates and admits one fixed-loop local Codex persistence invocation."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import click

from ...lib.constants.runtime import PersistenceProgress as Progress
from ...lib.constants.runtime import RuntimePaymentConfig as PaymentConfig
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
    RuntimeX402AdmissionRequest,
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
        @click.option(
            "--with-x402-payment",
            is_flag=True,
            help="Pay admission with x402 instead of API balance.",
        )
        @click.pass_obj
        def _run(
            context: Context,
            task: str,
            strength: int,
            key: str | None,
            with_x402_payment: bool,
        ) -> None:
            # Delegates without normalizing or wrapping the original task.
            self.execute(context, task, strength, key, with_x402_payment)

    def execute(
        self,
        context: Context,
        task: str,
        strength: int,
        key: str | None,
        with_x402_payment: bool = False,
    ) -> None:
        # Resolve local prerequisites before any wallet admission, then verify before execution.
        progress = context.output().diagnostic
        progress(Progress.PREPARING)
        key = key or str(uuid4())
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key) is None:
            raise click.BadParameter(
                "Use 8–128 letters, digits, dots, underscores, colons or hyphens."
            )
        plan = context.runtime_launch_planner().build(
            task, RuntimeHost.CODEX, Path.cwd(), "runtime.persistence@1"
        )
        settings = PersistenceSettings(strength=PersistenceStrength(strength))
        progress(Progress.CREDENTIALS)
        session = self._session(context)
        session.prepare(plan)
        endpoints = context.runtime_endpoints()
        progress(f"Admission recovery key: {key}")
        if with_x402_payment:
            from ...lib.api.runtime_payment import RuntimePayment

            payer = RuntimePayment(context.environment, PaymentConfig.PERSISTENCE_CENTS)
            progress(Progress.X402_ADMISSION)
            request = RuntimeX402AdmissionRequest(host=plan.host)
            grant = endpoints.admit_persistence_x402(request, key, payer)
        else:
            progress(Progress.ADMISSION)
            grant = endpoints.admit_persistence(RuntimeAdmissionRequest(host=plan.host), key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        progress(Progress.VERIFYING)
        verified = endpoints.verify_grant(
            RuntimeGrantVerificationRequest(
                grant_token=grant.grant_token,
                idempotency_key_hash=RuntimeAdmissionGate.hash_idempotency_key(key),
            )
        )
        verdict = RuntimeAdmissionGate().verify_online(plan, grant, verified)
        if not verdict.admitted:
            raise RuntimeAdmissionNotVerified(verdict.reason)
        progress(Progress.ADMITTED)
        result = context.runtime_executor().execute_persistence(plan, settings, session, verdict)
        context.output().result(
            OutputDocument(kind="runtime.persistence", data=result.model_dump(mode="json")),
            result.text,
        )

    def _session(self, context: Context) -> PersistentCodexSession:
        # The SDK merges env with the parent: empty overrides prevent secret reinheritance.
        credentials = context.require_provider_credentials(Provider.OPENAI)
        environment = dict(context.environment)
        for name in (
            *PROVIDER_ENV_VARS.values(),
            "GOOGLE_API_KEY",
            "VIDBYTE_API_KEY",
            "RUNTIME_ADMISSION_SIGNING_KEY",
            "CODEX_API_KEY",
            PaymentConfig.PRIVATE_KEY_ENV,
        ):
            environment[name] = ""
        environment["OPENAI_API_KEY"] = credentials.secret_value()
        return PersistentCodexSession(environment, context.output().diagnostic)
