"""`vidbyte-cli runtime same-host-ensemble` parses options and renders one ensemble run.

Roles are never supplied here: the first stage generates them, so this command's whole input
surface is one validated `EnsembleInputs` value plus an admission-scoped idempotency key.
Admission is bought and verified here — through the same layered gate every runtime
primitive uses — before the runner is allowed to start any agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import click
from pydantic import JsonValue, ValidationError

from ...lib.errors.failures import (
    EnsembleHostUnsupported,
    EnsembleInputsInvalid,
    RuntimeAdmissionNotVerified,
)
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...services.ensemble.runner import EnsembleRunner
from ...services.ensemble.sdk import EnsembleSdk
from ...types.ensemble import (
    EnsembleHost,
    EnsembleInputs,
    EnsembleReasoningEffort,
    EnsembleResult,
)
from ...types.research import IdempotencyKey
from ...types.runtime import (
    RuntimeAdmissionGrant,
    RuntimeAdmissionRequest,
    RuntimeCapabilityId,
    RuntimeHost,
    RuntimeLaunchPlan,
)

# The environment variable carrying the optional grant HMAC key. When it is absent the
# gate's Layer 1 typed-grant checks still gate; a present key additionally enables the
# Layer 2 signature check.
_VERIFICATION_KEY_ENV_VAR = "RUNTIME_ADMISSION_SIGNING_KEY"


class SameHostEnsembleCommand:
    """Validates ensemble options, admits and verifies, runs the primitive, renders."""

    def register(self, parent: click.Group) -> None:
        # Only Codex is offered, because it is the one host with verified fork and sandbox.
        @parent.command(
            name="same-host-ensemble",
            help=(
                "Run a planner-led team of Codex agents on this machine: generated roles "
                "propose approaches in read-only forks, a selector narrows them to one, "
                "and a single writer implements it. Costs a 2c admission per run."
            ),
        )
        @click.argument("task")
        @click.option(
            "--host",
            type=click.Choice(tuple(host.value for host in EnsembleHost)),
            default=EnsembleHost.CODEX.value,
            show_default=True,
            help=(
                "Which installed coding agent hosts the ensemble. Codex is the only host "
                "with verified thread-fork and per-fork sandbox support, so it is the "
                "only accepted value."
            ),
        )
        @click.option(
            "--roles",
            type=int,
            default=3,
            show_default=True,
            help=(
                "How many specialist roles the planner invents for this task (3-100). "
                "More roles widen the approach slate the selector narrows; every role "
                "runs concurrently in its own read-only fork against your subscription."
            ),
        )
        @click.option(
            "--model",
            default=None,
            help=(
                "Model override forwarded to every Codex turn and fork in the run. "
                "Omit to use the provider default."
            ),
        )
        @click.option(
            "--reasoning-effort",
            type=click.Choice(tuple(effort.value for effort in EnsembleReasoningEffort)),
            default=None,
            help=(
                "Reasoning effort forwarded to every Codex turn in the run "
                "(none, minimal, low, medium, high, xhigh). "
                "Omit to use the provider default."
            ),
        )
        @click.option(
            "--idempotency-key",
            "explicit_key",
            default=None,
            help=(
                "Reuse a key to retry a priced admission without being charged twice. "
                "Omit to generate one per invocation."
            ),
        )
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            task: str,
            host: str,
            roles: int,
            model: str | None,
            reasoning_effort: str | None,
            explicit_key: str | None,
        ) -> None:
            # Delegates parsed values to the class-owned execution method.
            self.execute(
                context,
                self._inputs(task, host, roles, model, reasoning_effort),
                explicit_key,
            )

    def execute(
        self,
        context: ApplicationContext,
        inputs: EnsembleInputs,
        explicit_key: str | None = None,
    ) -> None:
        # Everything free runs first: key validation, launch planning, host support, and
        # SDK resolution all complete before the one paid admission is requested, and the
        # layered gate verifies the grant before any agent is allowed to start.
        key = str(IdempotencyKey.create(explicit_key))
        plan = context.runtime_launch_planner().build(
            RuntimeCapabilityId.SAME_HOST_ENSEMBLE,
            inputs.task,
            RuntimeHost(inputs.host.value),
            Path.cwd(),
        )
        if plan.host is not RuntimeHost.CODEX:
            raise EnsembleHostUnsupported(plan.host.value)
        sdk = EnsembleSdk.load()
        grant = context.runtime_endpoints().admit_same_host_ensemble(
            RuntimeAdmissionRequest(host=plan.host), key
        )
        self._verify(plan, grant, context)
        result = EnsembleRunner().run(plan, inputs, sdk, grant)
        self._render(context, result)

    def _verify(
        self,
        plan: RuntimeLaunchPlan,
        grant: RuntimeAdmissionGrant,
        context: ApplicationContext,
    ) -> None:
        # A rejected grant fails the run here, so no fork ever starts unverified.
        verdict = RuntimeAdmissionGate().verify(
            plan,
            grant,
            datetime.now(UTC),
            context.environment.get(_VERIFICATION_KEY_ENV_VAR),
        )
        if not verdict.admitted:
            raise RuntimeAdmissionNotVerified(verdict.reason)

    def _inputs(
        self,
        task: str,
        host: str,
        roles: int,
        model: str | None,
        reasoning_effort: str | None,
    ) -> EnsembleInputs:
        # Bounds live on the model, so they hold for any caller, not just this Click surface.
        try:
            return EnsembleInputs(
                task=task,
                host=EnsembleHost(host),
                roles=roles,
                model=model,
                reasoning_effort=(
                    None if reasoning_effort is None else EnsembleReasoningEffort(reasoning_effort)
                ),
            )
        except (ValidationError, ValueError) as error:
            raise EnsembleInputsInvalid(error) from error

    def _render(self, context: ApplicationContext, result: EnsembleResult) -> None:
        # The machine document carries every branch; the human summary leads with the outcome.
        document: JsonValue = result.model_dump(mode="json")
        context.output().result(
            OutputDocument(kind="runtime.ensemble", data={"ensemble": document}),
            self._summary(result),
        )

    def _summary(self, result: EnsembleResult) -> str:
        # Roles and failures are listed before the implementation, so partial runs are obvious.
        proposed, total = len(result.proposals), len(result.roles)
        lines = [f"{proposed}/{total} roles proposed {result.candidates} approaches:"]
        lines.extend(
            f"  {item.role}: {len(item.approaches)} approaches" for item in result.proposals
        )
        lines.extend(f"  {item.role}: failed ({item.reason})" for item in result.failures)
        lines.append(self._narrowing(result))
        selected, verdict = result.selected.candidate, result.selected.verdict
        lines.append(
            f"selected {selected.candidate_id} ({selected.role}, score {verdict.score}): "
            f"{selected.approach.title}"
        )
        lines.append(f"  {verdict.rationale}")
        lines.append("")
        lines.append(result.implementation)
        return "\n".join(lines)

    def _narrowing(self, result: EnsembleResult) -> str:
        # The ladder is the audit trail of the selection, so it prints even when it is short.
        widths = [str(result.candidates), *(str(len(item.kept)) for item in result.rounds)]
        return f"selection narrowed {' -> '.join(widths)} over {len(result.rounds)} round(s)"
