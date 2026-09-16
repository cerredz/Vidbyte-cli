"""Runs the SDK-backed suggestion generation, critique, and revision workflow."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any, Literal

from ...lib.errors.failures import (
    SuggestionInputInvalid,
    SuggestionProviderFailed,
    SuggestionSdkUnavailable,
)
from ...types.suggestions import (
    StopReason,
    SuggestionCandidateBatch,
    SuggestionContextPrimitive,
    SuggestionCritiqueArtifact,
    SuggestionDraft,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
)
from .categories import SuggestionCategories
from .context_bridge import SuggestionContextBridge
from .critique_agent import SuggestionCritiqueAgent
from .extra_compute import ExtraComputeService
from .generator_agent import AgentCall, SuggestionGeneratorAgent
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts
from .result import SuggestionResultBuilder, SuggestionWorkflowOutcome
from .sdk import SuggestionAgentSettingsInput, SuggestionSdk, SuggestionTextInput
from .selection import SuggestionSelection

_POOL_MULTIPLE = 2
_POOL_CAP = 40


class _WorkflowLimit(Exception):
    """Internal control flow for a caller-owned time or token boundary."""

    def __init__(self, reason: StopReason) -> None:
        self.reason = reason


class SuggestionService:
    """Coordinates independent SDK agents and deterministic selection boundaries."""

    def __init__(self, sdk: Any | None = None) -> None:
        # Injection keeps offline verification at the same typed agent boundary as production.
        self._sdk = sdk
        self._categories = SuggestionCategories()
        self._context_bridge = SuggestionContextBridge(self._categories)
        self._selection = SuggestionSelection()
        self._handoffs = SuggestionHandoffBuilder()
        self._prompts = SuggestionPrompts()
        self._generator = SuggestionGeneratorAgent(
            self._categories, self._prompts, self._context_bridge, self._handoffs
        )
        self._critic = SuggestionCritiqueAgent(
            self._categories, self._prompts, self._context_bridge
        )
        self._results = SuggestionResultBuilder(self._categories, self._selection, self._handoffs)

    def run(self, request: SuggestionRequest) -> SuggestionResult:
        """Validate one request, run the loop, and return a versioned result."""
        if not isinstance(request, SuggestionRequest):
            raise SuggestionInputInvalid()
        if request.settings.dry_run:
            return self._results.build(
                request, SuggestionWorkflowOutcome((), {}, StopReason.DRY_RUN)
            )
        sdk = self._sdk or SuggestionSdk.load()
        try:
            outcome = asyncio.run(self._run(request, sdk))
        except (SuggestionSdkUnavailable, SuggestionProviderFailed):
            raise
        except Exception as error:
            raise SuggestionProviderFailed(error) from error
        return self._results.build(request, outcome)

    async def _run(self, request: SuggestionRequest, sdk: Any) -> SuggestionWorkflowOutcome:
        started = time.monotonic()
        usage = {"tokens": 0, "agent_calls": 0, "generation_calls": 0, "critique_calls": 0}
        categories = request.settings.categories or self._categories.ids()
        pool_size = min(request.settings.requested_count * _POOL_MULTIPLE, _POOL_CAP)
        last_reviewed: tuple[SuggestionIdea, ...] = ()
        warnings: list[str] = list(request.context_warnings)
        drafts: SuggestionCandidateBatch | tuple[SuggestionDraft, ...]
        try:
            if request.settings.extra_compute:
                drafts = await ExtraComputeService(
                    self._categories, self._prompts, self._context_bridge
                ).generate(
                    request,
                    categories,
                    pool_size,
                    self._agent_callback(
                        sdk, request, started, usage, "generation", self._prompts.generator_system()
                    ),
                )
            else:
                drafts = await self._generator.generate(
                    request,
                    categories,
                    pool_size,
                    self._agent_callback(
                        sdk, request, started, usage, "generation", self._prompts.generator_system()
                    ),
                )
            current = self._generator.ideas_from_drafts(drafts, request)
            if not current:
                return SuggestionWorkflowOutcome(
                    (), usage, StopReason.COUNT_SHORTFALL, tuple(warnings)
                )

            for round_index in range(request.settings.rounds):
                self._check_limit(request, started, usage)
                artifact = await self._critic.critique(
                    request,
                    categories,
                    current,
                    self._agent_callback(
                        sdk, request, started, usage, "critique", self._prompts.critic_system()
                    ),
                )
                kept, revisions = self._critic.review(current, artifact)
                last_reviewed = self._results.merge_reviewed(
                    last_reviewed, self._results.finalize(kept, request)
                )
                if not revisions:
                    reason = (
                        StopReason.COMPLETED
                        if len(last_reviewed) >= request.settings.requested_count
                        else StopReason.COUNT_SHORTFALL
                    )
                    return SuggestionWorkflowOutcome(last_reviewed, usage, reason, tuple(warnings))
                if round_index == request.settings.rounds - 1:
                    return SuggestionWorkflowOutcome(
                        last_reviewed, usage, StopReason.ROUND_LIMIT, tuple(warnings)
                    )
                self._check_limit(request, started, usage)
                current = await self._generator.revise(
                    request,
                    categories,
                    revisions,
                    self._agent_callback(
                        sdk, request, started, usage, "revision", self._prompts.revision_system()
                    ),
                )
                if not current:
                    return SuggestionWorkflowOutcome(
                        last_reviewed, usage, StopReason.COUNT_SHORTFALL, tuple(warnings)
                    )
        except _WorkflowLimit as limit:
            return SuggestionWorkflowOutcome(last_reviewed, usage, limit.reason, tuple(warnings))
        return SuggestionWorkflowOutcome(
            last_reviewed, usage, StopReason.ROUND_LIMIT, tuple(warnings)
        )

    def _agent_callback(
        self,
        sdk: Any,
        request: SuggestionRequest,
        started: float,
        usage: dict[str, int],
        phase: str,
        system_prompt: str,
    ) -> AgentCall:
        # Binds shared accounting and schema validation to one stage collaborator callback.
        async def call(
            role: Literal["generator", "critic"],
            prompt: str,
            context: SuggestionContextPrimitive,
            model: str | None,
        ) -> Any:
            # The role determines the only structured schema accepted at this boundary.
            schema: type[Any] = (
                SuggestionCandidateBatch if role == "generator" else SuggestionCritiqueArtifact
            )
            return await self._call_agent(
                sdk,
                role,
                system_prompt,
                prompt,
                context,
                model,
                schema,
                request,
                started,
                usage,
                phase,
            )

        return call

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
        usage: dict[str, int],
        phase: str,
    ) -> Any:
        self._check_limit(request, started, usage)
        prompt = self._with_output_budget(prompt, request)
        settings = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role=role,
                system_prompt=system_prompt,
                context=context,
                output_schema=schema,
                provider=request.settings.provider,
                model=model,
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
        self._record_usage(reply, usage, phase)
        structured = getattr(reply, "structured", None)
        if isinstance(structured, schema):
            return structured
        if isinstance(structured, Mapping):
            return schema.model_validate(structured)
        raise ValueError(f"{phase} agent returned no structured artifact")

    def _check_limit(
        self, request: SuggestionRequest, started: float, usage: dict[str, int]
    ) -> None:
        if (
            request.settings.max_total_tokens is not None
            and usage["tokens"] >= request.settings.max_total_tokens
        ):
            raise _WorkflowLimit(StopReason.TOKEN_LIMIT)
        if self._remaining_seconds(request, started) == 0:
            raise _WorkflowLimit(StopReason.TIME_LIMIT)

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

    def _record_usage(self, reply: Any, usage: dict[str, int], phase: str) -> None:
        usage["agent_calls"] += 1
        usage[f"{phase}_calls"] = usage.get(f"{phase}_calls", 0) + 1
        codex = getattr(reply, "codex", None)
        snapshot = getattr(codex, "last_usage", None) or getattr(codex, "usage", None)
        tokens = int(getattr(snapshot, "total_tokens", 0) or 0)
        usage["tokens"] += max(tokens, 0)


__all__ = ["SuggestionService"]
