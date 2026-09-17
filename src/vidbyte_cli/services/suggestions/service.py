"""Runs the SDK-backed suggestion generation, critique, and refinement workflow."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import uuid4

from ...lib.errors.failures import (
    SuggestionInputInvalid,
    SuggestionProviderFailed,
    SuggestionSdkUnavailable,
)
from ...types.suggestions import (
    RunStatus,
    StopReason,
    SuggestionAgentContext,
    SuggestionCandidateBatch,
    SuggestionCriticContext,
    SuggestionCriticContextPrimitive,
    SuggestionDraft,
    SuggestionHorizon,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
)
from .categories import SuggestionCategories
from .extra_compute import ExtraComputeService
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts
from .sdk import (
    SuggestionAgentSession,
    SuggestionAgentSettingsInput,
    SuggestionSdk,
    SuggestionTextInput,
)
from .selection import SuggestionSelection

_POOL_MULTIPLE = 2
_POOL_CAP = 40
Ideas = tuple[SuggestionIdea, ...]
Usage = dict[str, int]


class _WorkflowLimit(Exception):
    """Internal control flow for a caller-owned time or token boundary."""

    def __init__(self, reason: StopReason) -> None:
        # Carries the exact terminal reason across asynchronous helper boundaries.
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _WorkflowOutcome:
    """Final ideas, critic history, accounting, and the reason the loop stopped."""

    ideas: Ideas
    critic_contexts: tuple[SuggestionCriticContext, ...]
    usage: Usage
    stop_reason: StopReason
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class _RunState:
    """Shared state for one bounded suggestion run."""

    request: SuggestionRequest
    sdk: Any
    categories: tuple[str, ...]
    started: float
    usage: Usage


@dataclass(frozen=True, slots=True)
class _AgentTurn:
    """One independent generator or critic call."""

    role: Literal["generator", "critic"]
    system_prompt: str
    prompt: str
    context: SuggestionAgentContext
    model: str | None
    schema: type[Any]
    phase: str


class SuggestionService:
    """Coordinates one generator conversation and independent critic reviews."""

    def __init__(self, sdk: Any | None = None) -> None:
        # Injection keeps offline verification at the same typed boundary as production.
        self._sdk = sdk
        self._categories = SuggestionCategories()
        self._selection = SuggestionSelection()
        self._handoffs = SuggestionHandoffBuilder()
        self._prompts = SuggestionPrompts()

    def run(self, request: SuggestionRequest) -> SuggestionResult:
        # Validates one request, runs the loop, and returns a versioned result.
        if not isinstance(request, SuggestionRequest):
            raise SuggestionInputInvalid()
        if request.settings.dry_run:
            return self._result(request, _WorkflowOutcome((), (), {}, StopReason.DRY_RUN))
        sdk = self._sdk or SuggestionSdk.load()
        try:
            outcome = asyncio.run(self._run(request, sdk))
        except (SuggestionSdkUnavailable, SuggestionProviderFailed):
            raise
        except Exception as error:
            raise SuggestionProviderFailed(error) from error
        return self._result(request, outcome)

    async def _run(self, request: SuggestionRequest, sdk: Any) -> _WorkflowOutcome:
        # Runs complete critic-to-generator cycles so no critic context is left unconsumed.
        state = _RunState(
            request,
            sdk,
            request.settings.categories or self._categories.ids(),
            time.monotonic(),
            {
                "tokens": 0,
                "agent_calls": 0,
                "generation_calls": 0,
                "critique_calls": 0,
                "refinement_calls": 0,
            },
        )
        contexts: list[SuggestionCriticContext] = []
        warnings = list(request.context_warnings)
        current: Ideas = ()
        seeded_context = request.settings.extra_compute
        try:
            if seeded_context:
                current = await self._fanout_ideas(state)
                session = self._generator_session(state, current)
            else:
                session = self._generator_session(state, ())
                pool_size = min(request.settings.requested_count * _POOL_MULTIPLE, _POOL_CAP)
                batch = await self._call_session(
                    state,
                    session,
                    self._prompts.generator_turn(request.goal, pool_size),
                    "generation",
                )
                current = self._ideas_from_drafts(batch, request)
            if not current:
                return self._outcome(current, contexts, state, StopReason.COUNT_SHORTFALL, warnings)
            if not seeded_context:
                sdk.replace_stage_context(
                    session,
                    self._stage_context(state, tuple(idea.to_draft() for idea in current)),
                )
                seeded_context = True
            for _round_index in range(request.settings.rounds):
                self._check_limit(state)
                critic_context = await self._critique(state, current)
                self._validate_critic_context(critic_context, current, request)
                contexts.append(critic_context)
                sdk.place_critic_context(
                    session,
                    SuggestionCriticContextPrimitive(critic_context),
                )
                self._check_limit(state)
                batch = await self._call_session(
                    state,
                    session,
                    self._prompts.refinement_turn(request.goal, request.settings.requested_count),
                    "refinement",
                )
                if seeded_context:
                    sdk.replace_stage_context(session, self._stage_context(state))
                    seeded_context = False
                refined = self._reconcile(batch, current, request)
                if not refined:
                    return self._outcome(
                        refined, contexts, state, StopReason.COUNT_SHORTFALL, warnings
                    )
                if self._same_slate(current, refined):
                    return self._completed_outcome(refined, contexts, state, warnings)
                current = refined
        except _WorkflowLimit as limit:
            return self._outcome(current, contexts, state, limit.reason, warnings)
        reason = StopReason.ROUND_LIMIT if current else StopReason.COUNT_SHORTFALL
        return self._outcome(current, contexts, state, reason, warnings)

    async def _fanout_ideas(self, state: _RunState) -> Ideas:
        # Produces the initial pool from isolated category generators in extra-compute mode.
        request = state.request
        pool_size = min(request.settings.requested_count * _POOL_MULTIPLE, _POOL_CAP)
        drafts = await ExtraComputeService(self._categories, self._prompts).generate(
            request,
            state.categories,
            pool_size,
            lambda role, prompt, context, model: self._call_agent(
                state,
                _AgentTurn(
                    role,
                    self._prompts.generator_system(),
                    prompt,
                    context,
                    model,
                    SuggestionCandidateBatch,
                    "generation",
                ),
            ),
        )
        return self._ideas_from_drafts(drafts, request)

    def _generator_session(self, state: _RunState, seed: Ideas) -> SuggestionAgentSession:
        # Creates the sole generator conversation, optionally seeded by fan-out candidates.
        context = self._stage_context(state, tuple(idea.to_draft() for idea in seed))
        settings = SuggestionAgentSettingsInput(
            role="generator",
            system_prompt=self._prompts.generator_system(),
            context=context,
            output_schema=SuggestionCandidateBatch,
            provider=state.request.settings.provider,
        )
        return cast(SuggestionAgentSession, state.sdk.agent_session(settings))

    async def _critique(self, state: _RunState, ideas: Ideas) -> SuggestionCriticContext:
        # Gives a fresh critic the whole current slate and the same bounded evidence.
        context = self._stage_context(state, tuple(idea.to_draft() for idea in ideas))
        prompt = self._prompts.critic_turn(state.request.goal, ", ".join(i.id for i in ideas))
        result = await self._call_agent(
            state,
            _AgentTurn(
                "critic",
                self._prompts.critic_system(),
                prompt,
                context,
                state.request.settings.critic_model,
                SuggestionCriticContext,
                "critique",
            ),
        )
        return cast(SuggestionCriticContext, result)

    async def _call_agent(self, state: _RunState, turn: _AgentTurn) -> Any:
        # Runs an independent model call for fan-out generation or whole-slate critique.
        self._check_limit(state)
        settings = state.sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role=turn.role,
                system_prompt=turn.system_prompt,
                context=turn.context,
                output_schema=turn.schema,
                provider=state.request.settings.provider,
                model=turn.model,
            )
        )
        agent = state.sdk.agent(settings)
        reply = await self._run_turn(state, agent, turn.prompt)
        self._record_usage(reply, state.usage, turn.phase)
        return self._structured(reply, turn.schema, turn.phase)

    async def _call_session(
        self, state: _RunState, session: SuggestionAgentSession, prompt: str, phase: str
    ) -> SuggestionCandidateBatch:
        # Advances the same generator thread and verifies that its identity stays stable.
        reply = await self._run_turn(state, session.agent, prompt)
        session.verify_thread()
        self._record_usage(reply, state.usage, phase)
        return cast(
            SuggestionCandidateBatch,
            self._structured(reply, SuggestionCandidateBatch, phase),
        )

    async def _run_turn(self, state: _RunState, agent: Any, prompt: str) -> Any:
        # Applies the caller's output and wall-clock limits to one SDK turn.
        text = self._with_output_budget(prompt, state.request)
        run_input = state.sdk.run_input(SuggestionTextInput(text, state.request.attachments))
        remaining = self._remaining_seconds(state)
        try:
            if remaining is None:
                return await agent.arun(run_input)
            async with asyncio.timeout(remaining):
                return await agent.arun(run_input)
        except TimeoutError as error:
            raise _WorkflowLimit(StopReason.TIME_LIMIT) from error

    def _structured(self, reply: Any, schema: type[Any], phase: str) -> Any:
        # Accepts the declared model or validates its serialized mapping at one boundary.
        structured = getattr(reply, "structured", None)
        if isinstance(structured, schema):
            return structured
        if isinstance(structured, Mapping):
            return schema.model_validate(structured)
        raise ValueError(f"{phase} agent returned no structured artifact")

    def _ideas_from_drafts(
        self,
        drafts: SuggestionCandidateBatch | tuple[SuggestionDraft, ...],
        request: SuggestionRequest,
    ) -> Ideas:
        # Assigns stable identifiers to the initial generator pool in returned order.
        values = drafts.ideas if isinstance(drafts, SuggestionCandidateBatch) else drafts
        return tuple(
            self._idea_from_draft(draft, request, f"idea-{index:03d}", 1, index)
            for index, draft in enumerate(values, 1)
        )

    def _reconcile(
        self, batch: SuggestionCandidateBatch, previous: Ideas, request: SuggestionRequest
    ) -> Ideas:
        # Preserves known IDs, assigns IDs to new ideas, and increments changed revisions.
        by_id = {idea.id: idea for idea in previous}
        seen: set[str] = set()
        next_id = max((int(idea.id.removeprefix("idea-")) for idea in previous), default=0) + 1
        reconciled: list[SuggestionIdea] = []
        for rank, draft in enumerate(batch.ideas, 1):
            idea_id = draft.idea_id
            clean = SuggestionDraft.model_validate(draft.model_dump(exclude={"idea_id"}))
            if idea_id is None:
                idea_id = f"idea-{next_id:03d}"
                next_id += 1
                revision = 1
            else:
                if idea_id in seen:
                    raise ValueError("refinement output repeated a candidate id")
                if idea_id not in by_id:
                    raise ValueError("refinement output referenced an unknown candidate id")
                original = by_id[idea_id]
                revision = original.revision + int(not self._same_draft(original.to_draft(), draft))
            seen.add(idea_id)
            reconciled.append(self._idea_from_draft(clean, request, idea_id, revision, rank))
        return tuple(reconciled)

    def _same_draft(self, before: SuggestionDraft, after: SuggestionDraft) -> bool:
        # Compares generator-owned content while ignoring the stable identity carrier.
        return before.model_dump(mode="json", exclude={"idea_id"}) == after.model_dump(
            mode="json", exclude={"idea_id"}
        )

    def _same_slate(self, before: Ideas, after: Ideas) -> bool:
        # Detects convergence across identity, order, and every generator-owned field.
        return tuple(item.to_draft() for item in before) == tuple(item.to_draft() for item in after)

    def _idea_from_draft(
        self,
        draft: SuggestionDraft,
        request: SuggestionRequest,
        idea_id: str,
        revision: int,
        rank: int,
    ) -> SuggestionIdea:
        # Builds one result idea and its deterministic handoff from generator-owned fields.
        values = draft.model_dump(exclude={"idea_id"})
        handoff = self._handoffs.build_draft(draft, request, idea_id, revision)
        return SuggestionIdea(
            **values,
            id=idea_id,
            revision=revision,
            rank=rank,
            handoff=handoff,
        )

    def _validate_critic_context(
        self, context: SuggestionCriticContext, ideas: Ideas, request: SuggestionRequest
    ) -> None:
        # Rejects critic anchors that do not exist in the reviewed slate or caller evidence.
        candidate_ids = {idea.id for idea in ideas}
        evidence_refs = {item.ref for item in request.context_items}
        for observation in context.observations:
            if not set(observation.candidate_ids) <= candidate_ids:
                raise ValueError("critic context referenced an unknown candidate id")
            if not set(observation.evidence_refs) <= evidence_refs:
                raise ValueError("critic context referenced unknown evidence")

    def _finalize(self, ideas: Ideas, request: SuggestionRequest) -> Ideas:
        # Applies deterministic eligibility checks and rebuilds handoffs before output.
        allowed = set(self._categories.ids())
        manifest_refs = {
            entry.ref for entry in request.context_manifest if entry.status != "omitted"
        }
        if not manifest_refs:
            manifest_refs = {item.ref for item in request.context_items}
        selected = self._selection.validate_categories(ideas, allowed)
        selected = self._selection.validate_evidence(selected, manifest_refs)
        selected = self._selection.deduplicate(selected)
        selected = self._selection.suppress_rejected(selected, self._rejected_terms(request))
        if request.settings.horizon is not SuggestionHorizon.ANY:
            selected = tuple(
                idea for idea in selected if idea.horizon.value == request.settings.horizon.value
            )
        selected = tuple(self._handoff_refresh(idea, request) for idea in selected)
        return self._selection.rank(selected, request.settings.requested_count)

    def _handoff_refresh(self, idea: SuggestionIdea, request: SuggestionRequest) -> SuggestionIdea:
        # Rebuilds the handoff after ranking and refinement changed the idea envelope.
        return idea.model_copy(update={"handoff": self._handoffs.build(idea, request)})

    def _stage_context(
        self, state: _RunState, candidates: tuple[SuggestionDraft, ...] = ()
    ) -> SuggestionAgentContext:
        # Builds the stage-local evidence, categories, and optional whole candidate slate.
        return SuggestionAgentContext.for_stage(
            state.request.context,
            self._categories.prompt_section(state.categories),
            candidates,
        )

    def _check_limit(self, state: _RunState) -> None:
        # Stops before starting another model turn when a caller-owned budget is exhausted.
        token_limit = state.request.settings.max_total_tokens
        if token_limit is not None and state.usage["tokens"] >= token_limit:
            raise _WorkflowLimit(StopReason.TOKEN_LIMIT)
        if self._remaining_seconds(state) == 0:
            raise _WorkflowLimit(StopReason.TIME_LIMIT)

    def _with_output_budget(self, prompt: str, request: SuggestionRequest) -> str:
        # Carries the caller's output ceiling into every typed model turn.
        limit = request.settings.max_output_tokens
        if limit is None:
            return prompt
        return f"{prompt}\n\nKeep the structured response within {limit} output tokens."

    def _remaining_seconds(self, state: _RunState) -> float | None:
        # Calculates the remaining wall-clock budget immediately before one call.
        limit = state.request.settings.timeout_seconds
        if limit is None:
            return None
        return max(limit - (time.monotonic() - state.started), 0.0)

    def _record_usage(self, reply: Any, usage: Usage, phase: str) -> None:
        # Aggregates SDK usage snapshots without requiring SDK imports in this module.
        usage["agent_calls"] += 1
        usage[f"{phase}_calls"] = usage.get(f"{phase}_calls", 0) + 1
        codex = getattr(reply, "codex", None)
        snapshot = getattr(codex, "last_usage", None) or getattr(codex, "usage", None)
        usage["tokens"] += max(int(getattr(snapshot, "total_tokens", 0) or 0), 0)

    def _rejected_terms(self, request: SuggestionRequest) -> tuple[str, ...]:
        # Extracts caller directions that deterministic output filtering must suppress.
        return tuple(
            item.content
            for item in request.context_items
            if item.kind in {"completed", "in_progress", "avoid", "mistakes", "forbidden"}
        )

    def _completed_outcome(
        self,
        ideas: Ideas,
        contexts: list[SuggestionCriticContext],
        state: _RunState,
        warnings: list[str],
    ) -> _WorkflowOutcome:
        # Marks a converged slate complete unless deterministic filters create a shortfall.
        finalized = self._finalize(ideas, state.request)
        reason = (
            StopReason.COMPLETED
            if len(finalized) >= state.request.settings.requested_count
            else StopReason.COUNT_SHORTFALL
        )
        return _WorkflowOutcome(finalized, tuple(contexts), state.usage, reason, tuple(warnings))

    def _outcome(
        self,
        ideas: Ideas,
        contexts: list[SuggestionCriticContext],
        state: _RunState,
        reason: StopReason,
        warnings: list[str],
    ) -> _WorkflowOutcome:
        # Finalizes the latest complete generator slate for every terminal path.
        finalized = self._finalize(ideas, state.request) if ideas else ()
        if (
            reason is StopReason.COMPLETED
            and len(finalized) < state.request.settings.requested_count
        ):
            reason = StopReason.COUNT_SHORTFALL
        return _WorkflowOutcome(finalized, tuple(contexts), state.usage, reason, tuple(warnings))

    def _result(self, request: SuggestionRequest, outcome: _WorkflowOutcome) -> SuggestionResult:
        # Converts internal accounting into the stable public result envelope.
        ideas = outcome.ideas
        warnings = list(outcome.warnings)
        if outcome.stop_reason is StopReason.COUNT_SHORTFALL and ideas:
            warnings.append(
                f"Only {len(ideas)} worthwhile suggestions survived review; no filler was added."
            )
        status = (
            RunStatus.NO_SUGGESTIONS
            if not ideas
            else RunStatus.COMPLETE
            if outcome.stop_reason is StopReason.COMPLETED
            else RunStatus.PARTIAL
        )
        present_kinds = {item.kind for item in request.context_items}
        missing = tuple(
            kind
            for kind in (
                "completed",
                "in_progress",
                "decision",
                "constraint",
                "risks",
                "trajectory",
            )
            if kind not in present_kinds
        )
        return SuggestionResult(
            run_id=f"sug-{uuid4().hex[:12]}",
            status=status,
            goal=request.goal,
            requested_count=request.settings.requested_count,
            returned_count=len(ideas),
            settings=request.settings,
            context_manifest=request.context_manifest,
            ideas=ideas,
            critic_contexts=outcome.critic_contexts,
            category_coverage=self._selection.coverage(ideas),
            missing_context=missing,
            warnings=tuple(dict.fromkeys(warnings)),
            usage=outcome.usage,
            stop_reason=outcome.stop_reason,
            prompt_version=request.prompt_version,
        )


__all__ = ["SuggestionService"]
