"""Runs the SDK-backed suggestion generation, critique, and revision workflow.

One generator agent owns the whole run: its first turn drafts the slate, and each
later turn carries one general critic handoff and returns the complete revised
slate on the same native thread, so every critic handoff stays in its history.
Message tools let the generator stop the run to ask its parent for input, and let
a critic stop its review early to message the generator directly.
"""

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
    SuggestionCriticHandoff,
    SuggestionDraft,
    SuggestionFeedback,
    SuggestionHorizon,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
)
from .categories import SuggestionCategories
from .extra_compute import ExtraComputeService
from .handoff import SuggestionHandoffBuilder
from .message_tools import SuggestionMessageTool
from .project import REJECTED_FEEDBACK_KIND, SuggestionProject, SuggestionProjectKey
from .prompts.library import SuggestionPrompts
from .sdk import (
    SuggestionAgent,
    SuggestionAgentSettingsInput,
    SuggestionSdk,
    SuggestionTextInput,
)
from .selection import SuggestionSelection

# The first draft is wider than the request so revision has material to cut.
_POOL_MULTIPLE = 2
_POOL_CAP = 40


class _WorkflowLimit(Exception):
    """Internal control flow for a caller-owned time or token boundary."""

    def __init__(self, reason: StopReason) -> None:
        self.reason = reason


class _AgentMessage(Exception):
    """Internal control flow for an agent that stopped its turn by sending a message."""

    def __init__(self, message: str) -> None:
        self.message = message


@dataclass(frozen=True, slots=True)
class _WorkflowOutcome:
    """Final ideas plus accounting and the reason the loop stopped."""

    ideas: tuple[SuggestionIdea, ...]
    usage: dict[str, int]
    stop_reason: StopReason
    warnings: tuple[str, ...] = ()
    parent_message: str | None = None


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
        # A dry run validates inputs and reports settings without loading the SDK.
        if request.settings.dry_run:
            return self._result(request, _WorkflowOutcome((), {}, StopReason.DRY_RUN))
        sdk = self._sdk or SuggestionSdk.load()
        # Every unexpected failure inside the loop surfaces as one typed provider failure.
        try:
            outcome = asyncio.run(self._run(request, sdk))
        except (SuggestionSdkUnavailable, SuggestionProviderFailed):
            raise
        except Exception as error:
            raise SuggestionProviderFailed(error) from error
        return self._result(request, outcome)

    async def _run(self, request: SuggestionRequest, sdk: Any) -> _WorkflowOutcome:
        # Accounting and caller thresholds shared by every agent turn in this run.
        started = time.monotonic()
        usage = {"tokens": 0, "agent_calls": 0, "generation_calls": 0, "critique_calls": 0}
        categories = request.settings.categories or self._categories.ids()
        pool_size = min(request.settings.requested_count * _POOL_MULTIPLE, _POOL_CAP)
        warnings: list[str] = list(request.context_warnings)
        current: tuple[SuggestionIdea, ...] = ()
        # Only the persistent generator can reach the parent; its message ends the run.
        parent = SuggestionMessageTool("message_parent", self._prompts)
        try:
            if request.settings.extra_compute:
                # Extra compute drafts in fresh per-category agents, then seeds the one
                # persistent generator with the merged pool so revision keeps one thread.
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
                        usage,
                        "generation",
                    ),
                )
                current = self._ideas_from_drafts(drafts, request, 1)
                seed = tuple(idea.to_draft() for idea in current)
                generator = self._generator(request, sdk, categories, parent, seed)
            else:
                # The generator drafts the first slate on the thread it keeps for the run.
                generator = self._generator(request, sdk, categories, parent)
                batch = await self._ask(
                    sdk,
                    generator,
                    self._prompts.generator_turn(request.goal, pool_size),
                    SuggestionCandidateBatch,
                    request,
                    started,
                    usage,
                    "generation",
                    parent,
                )
                current = self._ideas_from_drafts(batch.ideas, request, 1)
            if not current:
                return _WorkflowOutcome((), usage, StopReason.COUNT_SHORTFALL, tuple(warnings))

            messages = 0
            for round_index in range(request.settings.rounds):
                # A fresh critic grades the latest slate and returns one general handoff.
                # It gets the message tool only while the caller's --max-messages remains.
                critic_tool = (
                    SuggestionMessageTool("message_generator", self._prompts)
                    if messages < request.settings.max_messages
                    else None
                )
                try:
                    handoff = await self._critique(
                        request, sdk, categories, current, started, usage, critic_tool
                    )
                    prompt = self._prompts.revision_turn(
                        request.goal, request.settings.requested_count, handoff.handoff
                    )
                except _AgentMessage as sent:
                    # A critic that stopped early sends its message in place of the review.
                    messages += 1
                    prompt = self._prompts.critic_message_turn(
                        request.goal, request.settings.requested_count, sent.message
                    )
                # The handoff is the generator's next turn, so its thread accumulates
                # generation, critique, revision, critique, ... across every round.
                batch = await self._ask(
                    sdk,
                    generator,
                    prompt,
                    SuggestionCandidateBatch,
                    request,
                    started,
                    usage,
                    "revision",
                    parent,
                )
                # The generator owns the slate, so its complete reply replaces the last one.
                current = self._ideas_from_drafts(batch.ideas, request, round_index + 2)
                if not current:
                    break
        except _AgentMessage as sent:
            # The generator asked its parent for input, so the run stops without a slate.
            return _WorkflowOutcome(
                (), usage, StopReason.PARENT_MESSAGE, tuple(warnings), sent.message
            )
        except _WorkflowLimit as limit:
            # A caller threshold ends the run with the latest generator-owned slate.
            return _WorkflowOutcome(
                self._finalize(current, request), usage, limit.reason, tuple(warnings)
            )
        ideas = self._finalize(current, request)
        reason = (
            StopReason.COMPLETED
            if len(ideas) >= request.settings.requested_count
            else StopReason.COUNT_SHORTFALL
        )
        return _WorkflowOutcome(ideas, usage, reason, tuple(warnings))

    def _generator(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        parent: SuggestionMessageTool,
        candidates: tuple[SuggestionDraft, ...] = (),
    ) -> SuggestionAgent:
        # Builds the run's single generator; reusing the object resumes its native thread.
        return self._agent(
            sdk,
            "generator",
            self._prompts.generator_system(),
            self._stage_context(request, categories, candidates),
            None,
            SuggestionCandidateBatch,
            request,
            (parent,),
        )

    async def _critique(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        ideas: tuple[SuggestionIdea, ...],
        started: float,
        usage: dict[str, int],
        tool: SuggestionMessageTool | None,
    ) -> SuggestionCriticHandoff:
        # Each round gets an independent critic that sees the slate but no generator history.
        context = self._stage_context(request, categories, tuple(idea.to_draft() for idea in ideas))
        ids = ", ".join(idea.id for idea in ideas)
        prompt = self._prompts.critic_turn(request.goal, ids)
        return cast(
            SuggestionCriticHandoff,
            await self._call_agent(
                sdk,
                "critic",
                self._prompts.critic_system(),
                prompt,
                context,
                request.settings.critic_model,
                SuggestionCriticHandoff,
                request,
                started,
                usage,
                "critique",
                tool,
            ),
        )

    async def _call_agent(
        self,
        sdk: Any,
        role: Literal["generator", "critic"],
        system_prompt: str,
        prompt: str,
        context: SuggestionAgentContext,
        model: str | None,
        schema: type[Any],
        request: SuggestionRequest,
        started: float,
        usage: dict[str, int],
        phase: str,
        tool: SuggestionMessageTool | None = None,
    ) -> Any:
        # One fresh agent answering one turn: the critic and extra-compute fan-out shape.
        self._check_limit(request, started, usage)
        tools = () if tool is None else (tool,)
        agent = self._agent(sdk, role, system_prompt, context, model, schema, request, tools)
        return await self._ask(sdk, agent, prompt, schema, request, started, usage, phase, tool)

    def _agent(
        self,
        sdk: Any,
        role: Literal["generator", "critic"],
        system_prompt: str,
        context: SuggestionAgentContext,
        model: str | None,
        schema: type[Any],
        request: SuggestionRequest,
        tools: tuple[SuggestionMessageTool, ...] = (),
    ) -> SuggestionAgent:
        # Every agent is read-only and bound to one output schema for all of its turns.
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
        return cast(SuggestionAgent, sdk.agent(settings))

    async def _ask(
        self,
        sdk: Any,
        agent: SuggestionAgent,
        prompt: str,
        schema: type[Any],
        request: SuggestionRequest,
        started: float,
        usage: dict[str, int],
        phase: str,
        tool: SuggestionMessageTool | None = None,
    ) -> Any:
        # Runs one turn inside the caller's time and token limits and parses its artifact.
        self._check_limit(request, started, usage)
        run_input = sdk.run_input(
            SuggestionTextInput(self._with_output_budget(prompt, request), request.attachments)
        )
        remaining = self._remaining_seconds(request, started)
        try:
            if remaining is None:
                reply = await self._arun(agent, run_input, tool)
            else:
                async with asyncio.timeout(remaining):
                    reply = await self._arun(agent, run_input, tool)
        except TimeoutError as error:
            raise _WorkflowLimit(StopReason.TIME_LIMIT) from error
        except _AgentMessage:
            # A stopped turn still counts as a call, but it returns no provider usage.
            self._record_usage(None, usage, phase)
            raise
        self._record_usage(reply, usage, phase)
        structured = getattr(reply, "structured", None)
        if isinstance(structured, schema):
            return structured
        if isinstance(structured, Mapping):
            return schema.model_validate(structured)
        raise ValueError(f"{phase} agent returned no structured artifact")

    async def _arun(
        self, agent: SuggestionAgent, run_input: Any, tool: SuggestionMessageTool | None
    ) -> Any:
        # A message tool stops the turn: the run is cancelled as soon as its message lands,
        # so nothing the model does after the call can reach the workflow.
        if tool is None:
            return await agent.arun(run_input)
        run = asyncio.ensure_future(agent.arun(run_input))
        stop = asyncio.ensure_future(tool.stopped.wait())
        try:
            await asyncio.wait((run, stop), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (run, stop):
                task.cancel()
        # The message wins even when the turn also finished, because the call means stop.
        if tool.message is not None:
            await asyncio.gather(run, return_exceptions=True)
            raise _AgentMessage(tool.message)
        return run.result()

    def _ideas_from_drafts(
        self, drafts: tuple[SuggestionDraft, ...], request: SuggestionRequest, revision: int
    ) -> tuple[SuggestionIdea, ...]:
        # Identity is positional, which is how the critic and the revision turn name candidates.
        return tuple(
            self._idea_from_draft(draft, request, f"idea-{index:03d}", revision, index)
            for index, draft in enumerate(drafts, 1)
        )

    def _idea_from_draft(
        self,
        draft: SuggestionDraft,
        request: SuggestionRequest,
        idea_id: str,
        revision: int,
        rank: int,
    ) -> SuggestionIdea:
        # Adds CLI-owned identity and a provisional handoff to one model draft.
        values = draft.model_dump(exclude={"idea_id"})
        handoff = self._handoffs.build_draft(draft, request, idea_id, revision)
        return SuggestionIdea(**values, id=idea_id, revision=revision, rank=rank, handoff=handoff)

    def _finalize(
        self, ideas: tuple[SuggestionIdea, ...], request: SuggestionRequest
    ) -> tuple[SuggestionIdea, ...]:
        # Deterministic gates the model cannot talk its way past, applied to the final slate.
        allowed = set(self._categories.ids())
        manifest_refs = {
            entry.ref for entry in request.context_manifest if entry.status != "omitted"
        }
        # Without a manifest, the supplied context items are the only citable evidence.
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
        # Handoffs are rebuilt last so they embed only evidence that survived the gates.
        selected = tuple(self._handoff_refresh(idea, request) for idea in selected)
        return self._selection.rank(selected, request.settings.requested_count)

    def _handoff_refresh(self, idea: SuggestionIdea, request: SuggestionRequest) -> SuggestionIdea:
        # Replaces the provisional draft handoff with the final evidence-bearing one.
        return idea.model_copy(update={"handoff": self._handoffs.build(idea, request)})

    def _stage_context(
        self,
        request: SuggestionRequest,
        categories: tuple[str, ...],
        candidates: tuple[SuggestionDraft, ...] = (),
    ) -> SuggestionAgentContext:
        # One window type per stage: what a stage omits, it simply never passes here.
        return SuggestionAgentContext.for_stage(
            request.context,
            self._categories.prompt_section(categories),
            candidates,
        )

    def _check_limit(
        self, request: SuggestionRequest, started: float, usage: dict[str, int]
    ) -> None:
        # Raised before a turn starts, so a limit never discards a finished reply.
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
        # None means no deadline; zero means the deadline has already passed.
        limit = request.settings.timeout_seconds
        if limit is None:
            return None
        remaining = limit - (time.monotonic() - started)
        return max(remaining, 0.0)

    def _record_usage(self, reply: Any, usage: dict[str, int], phase: str) -> None:
        # Counts calls per phase and adds the provider's token total when it reports one.
        usage["agent_calls"] += 1
        usage[f"{phase}_calls"] = usage.get(f"{phase}_calls", 0) + 1
        codex = getattr(reply, "codex", None)
        snapshot = getattr(codex, "last_usage", None) or getattr(codex, "usage", None)
        tokens = int(getattr(snapshot, "total_tokens", 0) or 0)
        usage["tokens"] += max(tokens, 0)

    def _rejected_terms(self, request: SuggestionRequest) -> tuple[str, ...]:
        # Rejected project feedback carries a label and optional reason, so only its verbatim
        # suggestion text is used as a suppression needle.
        terms: list[str] = []
        for item in request.context_items:
            if item.kind == REJECTED_FEEDBACK_KIND:
                terms.append(SuggestionFeedback.suggestion_from_context(item.content))
            elif item.kind in {"completed", "in_progress", "avoid", "mistakes", "forbidden"}:
                terms.append(item.content)
        return tuple(terms)

    def _result(self, request: SuggestionRequest, outcome: _WorkflowOutcome) -> SuggestionResult:
        # Converts the loop outcome into the versioned envelope the command renders.
        ideas = outcome.ideas
        warnings = list(outcome.warnings)
        if outcome.stop_reason is StopReason.COUNT_SHORTFALL and ideas:
            warnings.append(
                f"Only {len(ideas)} worthwhile suggestions survived review; no filler was added."
            )
        status = (
            RunStatus.NEEDS_INPUT
            if outcome.stop_reason is StopReason.PARENT_MESSAGE
            else RunStatus.NO_SUGGESTIONS
            if not ideas
            else RunStatus.COMPLETE
            if outcome.stop_reason is StopReason.COMPLETED
            else RunStatus.PARTIAL
        )
        # Names the context kinds the caller never supplied, so gaps are visible, not guessed.
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
            project_key=request.project_key,
            requested_count=request.settings.requested_count,
            returned_count=len(ideas),
            settings=request.settings,
            context_manifest=request.context_manifest,
            ideas=ideas,
            category_coverage=self._selection.coverage(ideas),
            missing_context=missing,
            warnings=tuple(dict.fromkeys(warnings)),
            usage=outcome.usage,
            stop_reason=outcome.stop_reason,
            parent_message=outcome.parent_message,
            feedback_capture=(
                SuggestionProject.feedback_capture(SuggestionProjectKey(request.project_key))
                if request.project_key
                else None
            ),
            prompt_version=request.prompt_version,
        )


__all__ = ["SuggestionService"]
