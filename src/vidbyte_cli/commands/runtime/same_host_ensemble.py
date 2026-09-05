"""`vidbyte-cli runtime same-host-ensemble` parses options and renders one ensemble run.

Roles are never supplied here: the first stage generates them, so this command's whole input
surface is one validated `EnsembleInputs` value. Everything after validation belongs to
`services/ensemble/`.
"""

from __future__ import annotations

from pathlib import Path

import click
from pydantic import JsonValue, ValidationError

from ...lib.errors.failures import EnsembleHostUnsupported, EnsembleInputsInvalid
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...services.ensemble.runner import EnsembleRunner
from ...types.ensemble import (
    EnsembleHost,
    EnsembleInputs,
    EnsembleReasoningEffort,
    EnsembleResult,
)
from ...types.runtime import RuntimeCapabilityId, RuntimeHost


class SameHostEnsembleCommand:
    """Validates ensemble options, runs the primitive, and renders its result."""

    def register(self, parent: click.Group) -> None:
        # Only Codex is offered, because it is the one host with verified fork and sandbox.
        @parent.command(
            name="same-host-ensemble", help="Run a role-differentiated agent ensemble locally"
        )
        @click.argument("task")
        @click.option(
            "--host",
            type=click.Choice(tuple(host.value for host in EnsembleHost)),
            default=EnsembleHost.CODEX.value,
            show_default=True,
            help="Native host to run on.",
        )
        @click.option(
            "--roles",
            type=int,
            default=3,
            show_default=True,
            help="How many roles the planner generates (3-100).",
        )
        @click.option("--model", default=None, help="Optional provider model override.")
        @click.option(
            "--reasoning-effort",
            type=click.Choice(tuple(effort.value for effort in EnsembleReasoningEffort)),
            default=None,
            help="Optional provider reasoning-effort override.",
        )
        @click.option(
            "--role-timeout",
            type=int,
            default=300,
            show_default=True,
            help="Seconds one role may take before it is recorded as failed.",
        )
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            task: str,
            host: str,
            roles: int,
            model: str | None,
            reasoning_effort: str | None,
            role_timeout: int,
        ) -> None:
            # Delegates parsed values to the class-owned execution method.
            self.execute(
                context, self._inputs(task, host, roles, model, reasoning_effort, role_timeout)
            )

    def execute(self, context: ApplicationContext, inputs: EnsembleInputs) -> None:
        # Plans locally first, so a missing host fails before the runner charges anything.
        plan = context.runtime_launch_planner().build(
            RuntimeCapabilityId.SAME_HOST_ENSEMBLE,
            inputs.task,
            RuntimeHost(inputs.host.value),
            Path.cwd(),
        )
        if plan.host is not RuntimeHost.CODEX:
            raise EnsembleHostUnsupported(plan.host.value)
        result = EnsembleRunner(context.runtime_endpoints()).run(plan, inputs)
        self._render(context, result)

    def _inputs(
        self,
        task: str,
        host: str,
        roles: int,
        model: str | None,
        reasoning_effort: str | None,
        role_timeout: int,
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
                role_timeout_seconds=role_timeout,
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
