"""Runs the SDK-backed suggestion generation, critique, and tool-editing workflow."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
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
    SuggestionCandidateBatch,
    SuggestionCompletion,
    SuggestionContextPrimitive,
    SuggestionCritiqueArtifact,
    SuggestionDraft,
    SuggestionHorizon,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
    SuggestionRunAccounting,
)
from .categories import SuggestionCategories
from .extra_compute import ExtraComputeService
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts
from .sdk import SuggestionAgentSettingsInput, SuggestionSdk, SuggestionTextInput
from .selection import SuggestionSelection
from .store import SuggestionStore, ToolCallLimitReached
from .warnings import (
    SHORT_AGENT_CALL_LIMIT,
    SHORT_CURATION_FAILED,
    SHORT_CURATION_INCOMPLETE,
    SHORT_TIME_LIMIT,
    SHORT_TOKEN_LIMIT,
    SHORT_TOOL_CALL_LIMIT,
    guidance_agent_call_limit,
    guidance_curation_failed,
    guidance_curation_incomplete,
    guidance_time_limit,
    guidance_token_limit,
    guidance_tool_call_limit,
    prompt_with_guidance,
    short_count_shortfall,
)

_POOL_MULTIPLE = 2
_POOL_CAP = 40


class _WorkflowLimit(Exception):
    """Internal control flow for a caller-owned time or token boundary."""

    def __init__(self, reason: StopReason) -> None:
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _WorkflowOutcome:
    """Committed ideas plus accounting and the reason the loop stopped."""

    ideas: tuple[SuggestionIdea, ...]
    accounting: SuggestionRunAccounting
    stop_reason: StopReason
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CurationPassInput:
    """Strict, validated input for one isolated curation pass."""

    request: SuggestionRequest
    sdk: Any
    categories: tuple[str, ...]
    current: tuple[SuggestionIdea, ...]
    artifact: SuggestionCritiqueArtifact
    store: SuggestionStore
    started: float
    accounting: SuggestionRunAccounting
    warnings: list[str]
    guidance: str = ""
    remaining_rounds: int = 0

    def __post_init__(self) -> None:
        self._validate_participants()
        self._validate_state()
        self._validate_run_context()

    def _validate_participants(self) -> None:
        # Every actor in the pass must already be the validated typed object.
        if not isinstance(self.request, SuggestionRequest):
            raise TypeError("Curation pass request must be a SuggestionRequest.")
        if self.sdk is None:
            raise TypeError("Curation pass sdk must be provided.")
        if not isinstance(self.artifact, SuggestionCritiqueArtifact):
            raise TypeError("Curation pass artifact must be a SuggestionCritiqueArtifact.")
        if not isinstance(self.store, SuggestionStore):
            raise TypeError("Curation pass store must be a SuggestionStore.")

    def _validate_state(self) -> None:
        # The slate under curation must be well-typed even when it is empty.
        if not isinstance(self.categories, tuple) or not self.categories:
            raise TypeError("Curation pass categories must be a non-empty tuple.")
        if any(type(category) is not str or not category for category in self.categories):
            raise ValueError("Curation pass categories must contain only non-empty strings.")
        if not isinstance(self.current, tuple) or any(
            not isinstance(idea, SuggestionIdea) for idea in self.current
        ):
            raise TypeError("Curation pass current must be a tuple of SuggestionIdea.")

    def _validate_run_context(self) -> None:
        # Run-local clocks, counters, and collectors must keep their exact shapes.
        if isinstance(self.started, bool) or not isinstance(self.started, (int, float)):
            raise TypeError("Curation pass started must be a monotonic timestamp.")
        if not isinstance(self.accounting, SuggestionRunAccounting):
            raise TypeError("Curation pass accounting must be a SuggestionRunAccounting.")
        if type(self.warnings) is not list:
            raise TypeError("Curation pass warnings must be a mutable list.")
        if type(self.guidance) is not str:
            raise TypeError("Curation pass guidance must be a string.")
        if type(self.remaining_rounds) is not int or self.remaining_rounds < 0:
            raise ValueError("Curation pass remaining rounds must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class _CurationRetry:
    """Model-facing guidance for a curation pass the next round should retry."""

    guidance: str

    def __post_init__(self) -> None:
        if type(self.guidance) is not str or not self.guidance.strip():
            raise ValueError("Curation retry guidance must be a non-empty string.")


class SuggestionService:
    """Coordinates independent SDK agents and deterministic selection boundaries."""

    def __init__(self, sdk: Any | None = None) -> None:
        # Injection keeps offline verification at the same typed agent boundary as production.
        self._sdk = sdk
        self._categories = SuggestionCategories()
        self._selection = SuggestionSelection()
        self._handoffs = SuggestionHandoffBuilder()
        self._prompts = SuggestionPrompts()

    def run(self, request: SuggestionRequest) -> SuggestionResult:
        """Validate one request, run the loop, and return a versioned result."""
        if not isinstance(request, SuggestionRequest):
            raise SuggestionInputInvalid()
        if request.settings.dry_run:
            return self._result(
                request, _WorkflowOutcome((), SuggestionRunAccounting(), StopReason.DRY_RUN)
            )
        sdk = self._sdk or SuggestionSdk.load()
        try:
            outcome = asyncio.run(self._run(request, sdk))
        except (SuggestionSdkUnavailable, SuggestionProviderFailed):
            raise
        except Exception as error:
            raise SuggestionProviderFailed(error) from error
        return self._result(request, outcome)

    async def _run(self, request: SuggestionRequest, sdk: Any) -> _WorkflowOutcome:
        # Runs initial generation once, then lets the generator edit state for each review pass.
        started = time.monotonic()
        accounting = SuggestionRunAccounting()
        categories = request.settings.categories or self._categories.ids()
        pool_size = min(request.settings.requested_count * _POOL_MULTIPLE, _POOL_CAP)
        warnings: list[str] = list(request.context_warnings)
        pending_guidance = ""
        drafts: SuggestionCandidateBatch | tuple[SuggestionDraft, ...]
        store: SuggestionStore | None = None
        try:
            if request.settings.extra_compute:
                drafts = await ExtraComputeService(self._categories, self._prompts).generate(
                    request,
                    categories,
                    pool_size,
                    lambda role, prompt, context, model: self._call_agent(
                        sdk,
                        role,
                        self._prompts.generator_system(),
                        prompt,
                        context,
                        model,
                        SuggestionCandidateBatch,
                        request,
                        started,
                        accounting,
                        "generation",
                    ),
                )
            else:
                drafts = await self._generate(
                    request, sdk, categories, pool_size, started, accounting
                )
            current = self._ideas_from_drafts(drafts, request)
            if not current:
                return _WorkflowOutcome((), accounting, StopReason.COUNT_SHORTFALL, tuple(warnings))

            store = SuggestionStore(request, categories)
            store.seed(current)
            for round_index in range(request.settings.rounds):
                self._check_limit(request, started, accounting)
                current = store.snapshot()
                artifact = await self._critique(
                    request, sdk, categories, current, started, accounting
                )
                self._validate_critique(current, artifact)
                working = store.working_copy()
                before = working.mutation_count
                self._check_limit(request, started, accounting)
                curation = await self._run_curation(
                    CurationPassInput(
                        request,
                        sdk,
                        categories,
                        current,
                        artifact,
                        working,
                        started,
                        accounting,
                        warnings,
                        pending_guidance,
                        request.settings.rounds - round_index - 1,
                    )
                )
                pending_guidance = ""
                if isinstance(curation, _CurationRetry):
                    if round_index == request.settings.rounds - 1:
                        finalized = self._finalize(current, request)
                        warnings.append(curation.guidance)
                        return _WorkflowOutcome(
                            finalized, accounting, StopReason.PROVIDER_FAILED, tuple(warnings)
                        )
                    pending_guidance = curation.guidance
                    continue
                if isinstance(curation, _WorkflowOutcome):
                    return curation
                if working.mutation_count == before:
                    finalized = self._finalize(store.snapshot(), request)
                    reason = (
                        StopReason.COMPLETED
                        if len(finalized) >= request.settings.requested_count
                        else StopReason.COUNT_SHORTFALL
                    )
                    return _WorkflowOutcome(finalized, accounting, reason, tuple(warnings))
                store.commit_from(working)
                if round_index == request.settings.rounds - 1:
                    finalized = self._finalize(store.snapshot(), request)
                    return _WorkflowOutcome(
                        finalized, accounting, StopReason.ROUND_LIMIT, tuple(warnings)
                    )
        except _WorkflowLimit as limit:
            committed = self._finalize(store.snapshot(), request) if store else ()
            warnings.extend(self._limit_warnings(limit.reason, request, accounting))
            return _WorkflowOutcome(committed, accounting, limit.reason, tuple(warnings))
        committed = self._finalize(store.snapshot(), request) if store else ()
        return _WorkflowOutcome(committed, accounting, StopReason.ROUND_LIMIT, tuple(warnings))

    async def _generate(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        count: int,
        started: float,
        accounting: SuggestionRunAccounting,
    ) -> SuggestionCandidateBatch:
        context = self._agent_context(request, categories)
        prompt = self._prompts.generator_turn(request.goal, count)
        return cast(
            SuggestionCandidateBatch,
            await self._call_agent(
                sdk,
                "generator",
                self._prompts.generator_system(),
                prompt,
                context,
                None,
                SuggestionCandidateBatch,
                request,
                started,
                accounting,
                "generation",
            ),
        )

    async def _run_curation(
        self, passed: CurationPassInput
    ) -> SuggestionCompletion | _WorkflowOutcome | _CurationRetry:
        """Run one isolated curation pass, retry it, or return its safe partial outcome."""
        try:
            completion = await self._curate(
                passed.request,
                passed.sdk,
                passed.categories,
                passed.current,
                passed.artifact,
                passed.store,
                passed.started,
                passed.accounting,
                passed.guidance,
            )
        except _WorkflowLimit:
            raise
        except ToolCallLimitReached:
            passed.warnings.append(SHORT_TOOL_CALL_LIMIT)
            passed.warnings.append(guidance_tool_call_limit(passed.request.settings.max_tool_calls))
            finalized = self._finalize(passed.current, passed.request)
            return _WorkflowOutcome(
                finalized, passed.accounting, StopReason.TOOL_CALL_LIMIT, tuple(passed.warnings)
            )
        except Exception:
            passed.warnings.append(SHORT_CURATION_FAILED)
            return _CurationRetry(guidance_curation_failed(passed.remaining_rounds))
        if not completion.completed:
            passed.warnings.append(SHORT_CURATION_INCOMPLETE)
            return _CurationRetry(guidance_curation_incomplete(passed.remaining_rounds))
        return completion

    async def _critique(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        ideas: tuple[SuggestionIdea, ...],
        started: float,
        accounting: SuggestionRunAccounting,
    ) -> SuggestionCritiqueArtifact:
        context = self._agent_context(request, categories, ideas)
        ids = ", ".join(idea.id for idea in ideas)
        prompt = self._prompts.critic_turn(request.goal, ids)
        return cast(
            SuggestionCritiqueArtifact,
            await self._call_agent(
                sdk,
                "critic",
                self._prompts.critic_system(),
                prompt,
                context,
                request.settings.critic_model,
                SuggestionCritiqueArtifact,
                request,
                started,
                accounting,
                "critique",
            ),
        )

    async def _curate(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        current: tuple[SuggestionIdea, ...],
        artifact: SuggestionCritiqueArtifact,
        store: SuggestionStore,
        started: float,
        accounting: SuggestionRunAccounting,
        guidance: str = "",
    ) -> SuggestionCompletion:
        # Gives a fresh generator the critic data and a transactionally isolated tool surface.
        if type(guidance) is not str:
            raise TypeError("Curation guidance must be a string.")
        context = self._agent_context(request, categories, current)
        feedback = json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        feedback = feedback.replace("<", "\\u003c").replace(">", "\\u003e")
        prompt = prompt_with_guidance(
            self._prompts.curator_turn(request.goal, len(current)), guidance
        )
        return cast(
            SuggestionCompletion,
            await self._call_agent(
                sdk,
                "generator",
                self._prompts.generator_system(feedback),
                prompt,
                context,
                None,
                SuggestionCompletion,
                request,
                started,
                accounting,
                "curation",
                store.tools(),
            ),
        )

    async def _call_agent(
        self,
        sdk: Any,
        role: Literal["generator", "critic"],
        system_prompt: str,
        prompt: str,
        context: SuggestionContextPrimitive,
        model: str | None,
        schema: type[Any],
        request: SuggestionRequest,
        started: float,
        accounting: SuggestionRunAccounting,
        phase: Literal["generation", "critique", "curation"],
        tools: tuple[Any, ...] = (),
    ) -> Any:
        self._check_limit(request, started, accounting)
        accounting.note_attempt()
        prompt = self._with_output_budget(prompt, request)
        settings = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role=role,
                system_prompt=system_prompt,
                context=context,
                output_schema=schema,
                provider=request.settings.provider,
                model=model,
                tools=tools,
            )
        )
        agent = sdk.agent(settings)
        remaining = self._remaining_seconds(request, started)
        try:
            if remaining is None:
                reply = await agent.arun(sdk.run_input(SuggestionTextInput(prompt)))
            else:
                async with asyncio.timeout(remaining):
                    reply = await agent.arun(sdk.run_input(SuggestionTextInput(prompt)))
        except TimeoutError as error:
            raise _WorkflowLimit(StopReason.TIME_LIMIT) from error
        self._record_usage(reply, accounting, phase)
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
    ) -> tuple[SuggestionIdea, ...]:
        values = drafts.ideas if isinstance(drafts, SuggestionCandidateBatch) else drafts
        return tuple(
            self._idea_from_draft(
                draft, request, f"idea-{index:03d}", 1, index, "Awaiting independent critique."
            )
            for index, draft in enumerate(values, 1)
        )

    def _idea_from_draft(
        self,
        draft: SuggestionDraft,
        request: SuggestionRequest,
        idea_id: str,
        revision: int,
        rank: int,
        review_summary: str,
    ) -> SuggestionIdea:
        values = draft.model_dump(exclude={"idea_id"})
        handoff = self._handoffs.build_draft(draft, request, idea_id, revision)
        return SuggestionIdea(
            **values,
            id=idea_id,
            revision=revision,
            rank=rank,
            review_summary=review_summary,
            handoff=handoff,
        )

    def _validate_critique(
        self, ideas: tuple[SuggestionIdea, ...], artifact: SuggestionCritiqueArtifact
    ) -> None:
        # Checks exact candidate coverage without interpreting the critic's verdicts.
        identifiers = tuple(item.idea_id for item in artifact.critiques)
        expected = {idea.id for idea in ideas}
        if set(identifiers) != expected or len(identifiers) != len(set(identifiers)):
            raise ValueError("critic artifact must contain exactly one review for every candidate")

    def _finalize(
        self, ideas: tuple[SuggestionIdea, ...], request: SuggestionRequest
    ) -> tuple[SuggestionIdea, ...]:
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
        return idea.model_copy(update={"handoff": self._handoffs.build(idea, request)})

    def _agent_context(
        self,
        request: SuggestionRequest,
        categories: tuple[str, ...],
        ideas: tuple[SuggestionIdea, ...] = (),
    ) -> SuggestionContextPrimitive:
        candidate_handoffs = (
            json.dumps([idea.model_dump(mode="json") for idea in ideas], sort_keys=True)
            if ideas
            else ""
        )
        return replace(
            request.context,
            selected_categories=self._categories.prompt_section(categories),
            candidate_handoffs=candidate_handoffs,
        )

    def _check_limit(
        self, request: SuggestionRequest, started: float, accounting: SuggestionRunAccounting
    ) -> None:
        if accounting.agent_calls >= request.settings.max_agent_calls:
            raise _WorkflowLimit(StopReason.AGENT_CALL_LIMIT)
        if (
            request.settings.max_total_tokens is not None
            and accounting.tokens >= request.settings.max_total_tokens
        ):
            raise _WorkflowLimit(StopReason.TOKEN_LIMIT)
        if self._remaining_seconds(request, started) == 0:
            raise _WorkflowLimit(StopReason.TIME_LIMIT)

    def _limit_warnings(
        self,
        reason: StopReason,
        request: SuggestionRequest,
        accounting: SuggestionRunAccounting,
    ) -> tuple[str, str]:
        # Pairs the stable operator warning with the model-facing recovery guidance.
        if reason is StopReason.AGENT_CALL_LIMIT:
            return (
                SHORT_AGENT_CALL_LIMIT,
                guidance_agent_call_limit(request.settings.max_agent_calls, accounting.agent_calls),
            )
        if reason is StopReason.TOKEN_LIMIT:
            return (
                SHORT_TOKEN_LIMIT,
                guidance_token_limit(
                    cast(int, request.settings.max_total_tokens), accounting.tokens
                ),
            )
        return (
            SHORT_TIME_LIMIT,
            guidance_time_limit(cast(int, request.settings.timeout_seconds)),
        )

    def _with_output_budget(self, prompt: str, request: SuggestionRequest) -> str:
        # Carries the caller's generous output ceiling into every typed model turn.
        limit = request.settings.max_output_tokens
        if limit is None:
            return prompt
        return f"{prompt}\n\nKeep the structured response within {limit} output tokens."

    def _remaining_seconds(self, request: SuggestionRequest, started: float) -> float | None:
        limit = request.settings.timeout_seconds
        if limit is None:
            return None
        remaining = limit - (time.monotonic() - started)
        return max(remaining, 0.0)

    def _record_usage(
        self,
        reply: Any,
        accounting: SuggestionRunAccounting,
        phase: Literal["generation", "critique", "curation"],
    ) -> None:
        codex = getattr(reply, "codex", None)
        snapshot = getattr(codex, "last_usage", None) or getattr(codex, "usage", None)
        tokens = int(getattr(snapshot, "total_tokens", 0) or 0)
        accounting.note_completion(phase, max(tokens, 0))

    def _rejected_terms(self, request: SuggestionRequest) -> tuple[str, ...]:
        return tuple(
            item.content
            for item in request.context_items
            if item.kind in {"completed", "in_progress", "avoid", "mistakes", "forbidden"}
        )

    def _result(self, request: SuggestionRequest, outcome: _WorkflowOutcome) -> SuggestionResult:
        ideas = outcome.ideas
        warnings = list(outcome.warnings)
        if outcome.stop_reason is StopReason.COUNT_SHORTFALL and ideas:
            warnings.append(short_count_shortfall(len(ideas)))
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
            category_coverage=self._selection.coverage(ideas),
            missing_context=missing,
            warnings=tuple(dict.fromkeys(warnings)),
            usage=outcome.accounting.to_dict(),
            stop_reason=outcome.stop_reason,
            prompt_version=request.prompt_version,
        )


__all__ = ["CurationPassInput", "SuggestionService"]
