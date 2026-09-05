"""The four-stage algorithm: plan roles, propose in parallel, select down to one, implement.

Roles branch from the root thread rather than from each other, so their errors stay
decorrelated — that independence is the whole reason an ensemble beats one agent. The
selector and the implementer also branch from the root, so neither inherits a single role's
framing; the selector then runs several turns on its own thread, which is what lets a later
narrowing round build on the reasoning of the earlier ones.

A role that fails is recorded and stepped over; only an empty slate aborts the run.
"""

from __future__ import annotations

import asyncio
from math import ceil
from typing import Any, Literal

from ...lib.errors.failures import (
    EnsembleAllRolesFailed,
    EnsembleHostFailed,
    EnsembleImplementerFailed,
    EnsembleProposalUnusable,
    EnsembleRolePlanInvalid,
    EnsembleSelectionInvalid,
)
from ...types.ensemble import (
    ApproachCandidate,
    EnsembleResult,
    EnsembleRoleFailure,
    GeneratedRole,
    RolePlan,
    RoleProposal,
    SelectedApproach,
    SelectionRound,
)
from .sdk import EnsembleAgent
from .settings import EnsembleStages

RoleFailureReason = Literal["timeout", "host_error", "invalid_output"]
Proposals = tuple[RoleProposal, ...]
Candidates = tuple[ApproachCandidate, ...]

# Each round keeps a fifth of what it was given, so a thousand candidates reach one in five
# rounds while fifteen reach one in two. Narrowing this fast is what keeps the selector's
# context bounded; the ladder is computed here rather than chosen by the agent so a run's
# shape depends only on how many candidates exist.
_NARROWING_DIVISOR = 5


class EnsembleService:
    """Runs one same-host ensemble from a validated plan to a normalized result."""

    def __init__(self, stages: EnsembleStages) -> None:
        # One service instance per run; the stages object carries every shared collaborator.
        self._stages = stages

    def run(self, cents: int) -> EnsembleResult:
        # The single synchronous boundary; everything below it shares one event loop.
        return asyncio.run(self._orchestrate(cents))

    async def _orchestrate(self, cents: int) -> EnsembleResult:
        # Plan, fan out concurrently, narrow to one, implement; the root is the only ancestor.
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
        candidates = self._candidates(proposals)
        rounds, selected, selector_thread = await self._select(root, candidates)
        implementation, thread_id = await self._implement(root, selected, len(candidates))
        return EnsembleResult(
            task=inputs.task,
            host=inputs.host,
            roles=plan.roles,
            proposals=proposals,
            failures=failures,
            candidates=len(candidates),
            rounds=rounds,
            selected=selected,
            implementation=implementation,
            root_thread_id=root.thread_id,
            selector_thread_id=selector_thread,
            implementer_thread_id=thread_id,
            charged_cents=cents,
        )

    async def _plan_roles(self, root: EnsembleAgent) -> RolePlan:
        # One turn, which both mints the thread id forking requires and designs the roster.
        stages = self._stages
        prompt = stages.prompts.planner_turn_prompt(stages.inputs.task, stages.inputs.roles)
        try:
            reply = await root.arun(stages.sdk.run_input(prompt))
        # CancelledError is a BaseException, so Ctrl-C passes through this handler untouched.
        except Exception as error:
            if stages.sdk.is_schema_error(error):
                raise EnsembleRolePlanInvalid(stages.inputs.roles) from error
            raise EnsembleHostFailed("planner", error) from error
        plan = getattr(reply, "structured", None)
        if not isinstance(plan, RolePlan) or len(plan.roles) != stages.inputs.roles:
            raise EnsembleRolePlanInvalid(stages.inputs.roles)
        # Names label every candidate the selector sees, so duplicates would make ids ambiguous.
        if len({role.name for role in plan.roles}) != len(plan.roles):
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

    async def _select(
        self, root: EnsembleAgent, candidates: Candidates
    ) -> tuple[tuple[SelectionRound, ...], SelectedApproach, str]:
        # One selector thread across every round, so a later round sees its own earlier reasoning.
        stages = self._stages
        try:
            agent = await root.afork(stages.selector())
        except Exception as error:
            raise EnsembleHostFailed("selector", error) from error
        rounds: list[SelectionRound] = []
        alive = candidates
        while True:
            number, target = len(rounds) + 1, self._target(len(alive))
            final = target == 1
            outcome = await self._round(agent, self._round_prompt(alive, number, target), target)
            rounds.append(outcome)
            alive = self._survivors(alive, outcome)
            if final:
                # The winner is joined back to its full proposal, which no agent resends.
                chosen = SelectedApproach(candidate=alive[0], verdict=outcome.kept[0])
                return tuple(rounds), chosen, agent.thread_id

    def _round_prompt(self, alive: Candidates, number: int, target: int) -> str:
        # The last round is authored separately: what it writes becomes the implementer brief.
        prompts, task = self._stages.prompts, self._stages.inputs.task
        if target == 1:
            return prompts.selector_final_prompt(task, alive, number)
        return prompts.selector_round_prompt(task, alive, number, target)

    async def _round(self, agent: EnsembleAgent, prompt: str, target: int) -> SelectionRound:
        # A round the host cannot complete ends the run: there is no partial way to narrow.
        stages = self._stages
        try:
            reply = await agent.arun(stages.sdk.run_input(prompt))
        except Exception as error:
            if stages.sdk.is_schema_error(error):
                raise EnsembleSelectionInvalid(target) from error
            raise EnsembleHostFailed("selector", error) from error
        outcome = getattr(reply, "structured", None)
        if not isinstance(outcome, SelectionRound) or len(outcome.kept) != target:
            raise EnsembleSelectionInvalid(target)
        return outcome

    def _survivors(self, alive: Candidates, outcome: SelectionRound) -> Candidates:
        # Kept ids are matched against the slate actually offered, never trusted as given.
        offered = {candidate.candidate_id: candidate for candidate in alive}
        kept = tuple(dict.fromkeys(verdict.candidate_id for verdict in outcome.kept))
        if len(kept) != len(outcome.kept) or any(item not in offered for item in kept):
            raise EnsembleSelectionInvalid(len(outcome.kept))
        return tuple(offered[item] for item in kept)

    def _target(self, alive: int) -> int:
        # Always narrows: a slate of five or fewer goes straight to the final round.
        return max(ceil(alive / _NARROWING_DIVISOR), 1)

    def _candidates(self, proposals: Proposals) -> Candidates:
        # Ids are assigned here so they are stable, compact, and checkable on the way back.
        return tuple(
            ApproachCandidate(
                candidate_id=f"{role_index}.{approach_index}",
                role=proposal.role,
                approach=approach,
            )
            for role_index, proposal in enumerate(proposals, 1)
            for approach_index, approach in enumerate(proposal.approaches, 1)
        )

    async def _implement(
        self, root: EnsembleAgent, selected: SelectedApproach, candidates: int
    ) -> tuple[str, str]:
        # Forks the root, not the selector, so it inherits the task but not the deliberation.
        stages = self._stages
        prompt = stages.prompts.implementer_turn_prompt(
            stages.inputs.task, selected, candidates, stages.inputs.roles
        )
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
