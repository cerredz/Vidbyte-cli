"""The three-stage fan-out/fan-in algorithm: plan roles, propose, then implement.

Roles branch from the root thread rather than from each other, so their errors stay
decorrelated — that independence is the whole reason an ensemble beats one agent. The
implementer also branches from the root, so it inherits the task and plan but no role's bias.

A role that fails is recorded and stepped over; only an empty proposal set aborts the run.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from ...lib.errors.failures import (
    EnsembleAllRolesFailed,
    EnsembleHostFailed,
    EnsembleImplementerFailed,
    EnsembleProposalUnusable,
    EnsembleRolePlanInvalid,
)
from ...types.ensemble import (
    EnsembleResult,
    EnsembleRoleFailure,
    GeneratedRole,
    RolePlan,
    RoleProposal,
)
from .sdk import EnsembleAgent
from .settings import EnsembleStages

RoleFailureReason = Literal["timeout", "host_error", "invalid_output"]
Proposals = tuple[RoleProposal, ...]


class EnsembleService:
    """Runs one same-host ensemble from a validated plan to a normalized result."""

    def __init__(self, stages: EnsembleStages) -> None:
        # One service instance per run; the stages object carries every shared collaborator.
        self._stages = stages

    def run(self, cents: int) -> EnsembleResult:
        # The single synchronous boundary; everything below it shares one event loop.
        return asyncio.run(self._orchestrate(cents))

    async def _orchestrate(self, cents: int) -> EnsembleResult:
        # Plan, fan out concurrently, fan in once; the root is the only shared ancestor.
        inputs = self._stages.inputs
        root = self._stages.sdk.agent(self._stages.root())
        plan = await self._plan_roles(root)
        outcomes = await asyncio.gather(
            *(self._propose(root, role) for role in plan.roles),
            return_exceptions=True,
        )
        proposals, failures = self._partition(plan.roles, list(outcomes))
        if not proposals:
            raise EnsembleAllRolesFailed(len(failures))
        implementation, thread_id = await self._implement(root, proposals)
        return EnsembleResult(
            task=inputs.task,
            host=inputs.host,
            roles=plan.roles,
            proposals=proposals,
            failures=failures,
            implementation=implementation,
            root_thread_id=root.thread_id,
            implementer_thread_id=thread_id,
            charged_cents=cents,
        )

    async def _plan_roles(self, root: EnsembleAgent) -> RolePlan:
        # One turn, which both mints the thread id forking requires and designs the roster.
        stages = self._stages
        prompt = stages.prompts.planner_turn_prompt(stages.inputs.task)
        try:
            reply = await root.arun(stages.sdk.run_input(prompt))
        # CancelledError is a BaseException, so Ctrl-C passes through this handler untouched.
        except Exception as error:
            raise EnsembleHostFailed("planner", error) from error
        plan = getattr(reply, "structured", None)
        if not isinstance(plan, RolePlan) or len(plan.roles) != stages.inputs.roles:
            raise EnsembleRolePlanInvalid(stages.inputs.roles)
        return plan

    async def _propose(self, root: EnsembleAgent, role: GeneratedRole) -> RoleProposal:
        # Bounded so one hung host cannot hold the fan-in open for every other role.
        stages = self._stages
        prompt = stages.prompts.role_turn_prompt(stages.inputs.task)
        async with asyncio.timeout(stages.inputs.role_timeout_seconds):
            agent = await root.afork(stages.proposal(role))
            reply = await agent.arun(stages.sdk.run_input(prompt))
        proposal = getattr(reply, "structured", None)
        if not isinstance(proposal, RoleProposal):
            raise EnsembleProposalUnusable(role.name)
        return proposal

    async def _implement(self, root: EnsembleAgent, taken: Proposals) -> tuple[str, str]:
        # Forks the root, not a role, so no single proposal's framing is inherited wholesale.
        stages = self._stages
        prompt = stages.prompts.implementer_turn_prompt(stages.inputs.task, taken)
        try:
            agent = await root.afork(stages.implementer())
            reply = await agent.arun(stages.sdk.run_input(prompt))
        except Exception as error:
            raise EnsembleImplementerFailed(error) from error
        return str(getattr(reply, "content", "")), agent.thread_id

    def _partition(self, roles: tuple[GeneratedRole, ...], outcomes: list[Any]) -> tuple[Any, Any]:
        # Survivors carry the run; a failed role becomes a record, never a raised error.
        proposals: list[RoleProposal] = []
        failures: list[EnsembleRoleFailure] = []
        for role, outcome in zip(roles, outcomes, strict=True):
            if isinstance(outcome, RoleProposal):
                proposals.append(outcome)
            elif isinstance(outcome, BaseException):
                failures.append(EnsembleRoleFailure(role=role.name, reason=self._reason(outcome)))
        return tuple(proposals), tuple(failures)

    def _reason(self, error: BaseException) -> RoleFailureReason:
        # Cancellation is re-raised rather than classified, so Ctrl-C still reaches the caller.
        if isinstance(error, asyncio.CancelledError):
            raise error
        if isinstance(error, TimeoutError):
            return "timeout"
        if isinstance(error, Exception) and self._stages.sdk.is_provider_error(error):
            return "host_error"
        return "invalid_output"
