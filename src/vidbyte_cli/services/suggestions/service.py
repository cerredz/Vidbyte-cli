"""Runs the SDK-backed suggestion generation, critique, and revision workflow."""

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
    CritiqueConfidence,
    CritiqueConstraint,
    CritiqueEvidenceCheck,
    CritiqueVerdict,
    RunStatus,
    StopReason,
    SuggestionCandidateBatch,
    SuggestionContextPrimitive,
    SuggestionCritique,
    SuggestionCritiqueArtifact,
    SuggestionDraft,
    SuggestionHorizon,
    SuggestionIdea,
    SuggestionRequest,
    SuggestionResult,
)
from .categories import SuggestionCategories
from .context_bridge import SuggestionContextBridge
from .extra_compute import ExtraComputeService
from .handoff import SuggestionHandoffBuilder
from .prompts.library import SuggestionPrompts
from .sdk import SuggestionAgentSettingsInput, SuggestionSdk, SuggestionTextInput
from .selection import SuggestionSelection

_POOL_MULTIPLE = 2
_POOL_CAP = 40


class _WorkflowLimit(Exception):
    """Internal control flow for a caller-owned time or token boundary."""

    def __init__(self, reason: StopReason) -> None:
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _WorkflowOutcome:
    """Fully reviewed ideas plus accounting and the reason the loop stopped."""

    ideas: tuple[SuggestionIdea, ...]
    usage: dict[str, int]
    stop_reason: StopReason
    warnings: tuple[str, ...] = ()


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

    def run(self, request: SuggestionRequest) -> SuggestionResult:
        """Validate one request, run the loop, and return a versioned result."""
        if not isinstance(request, SuggestionRequest):
            raise SuggestionInputInvalid()
        if request.settings.dry_run:
            return self._result(request, _WorkflowOutcome((), {}, StopReason.DRY_RUN))
        sdk = self._sdk or SuggestionSdk.load()
        try:
            outcome = asyncio.run(self._run(request, sdk))
        except (SuggestionSdkUnavailable, SuggestionProviderFailed):
            raise
        except Exception as error:
            raise SuggestionProviderFailed(error) from error
        return self._result(request, outcome)

    async def _run(self, request: SuggestionRequest, sdk: Any) -> _WorkflowOutcome:
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
            else:
                drafts = await self._generate(request, sdk, categories, pool_size, started, usage)
            current = self._ideas_from_drafts(drafts, request)
            if not current:
                return _WorkflowOutcome((), usage, StopReason.COUNT_SHORTFALL, tuple(warnings))

            for round_index in range(request.settings.rounds):
                self._check_limit(request, started, usage)
                artifact = await self._critique(request, sdk, categories, current, started, usage)
                kept, revisions = self._review(current, artifact)
                last_reviewed = self._merge_reviewed(last_reviewed, self._finalize(kept, request))
                if not revisions:
                    reason = (
                        StopReason.COMPLETED
                        if len(last_reviewed) >= request.settings.requested_count
                        else StopReason.COUNT_SHORTFALL
                    )
                    return _WorkflowOutcome(last_reviewed, usage, reason, tuple(warnings))
                if round_index == request.settings.rounds - 1:
                    return _WorkflowOutcome(
                        last_reviewed, usage, StopReason.ROUND_LIMIT, tuple(warnings)
                    )
                self._check_limit(request, started, usage)
                current = await self._revise(
                    request, sdk, categories, current, revisions, started, usage
                )
                before = {idea.id: idea for idea, _ in revisions}
                unchanged = tuple(
                    idea
                    for idea in current
                    if idea.id in before and self._same_candidate_content(before[idea.id], idea)
                )
                if unchanged:
                    warnings.append(
                        f"Stopped {len(unchanged)} unchanged suggestion revision(s) "
                        "before another critique."
                    )
                    current = tuple(idea for idea in current if idea not in unchanged)
                if not current:
                    return _WorkflowOutcome(
                        last_reviewed, usage, StopReason.COUNT_SHORTFALL, tuple(warnings)
                    )
        except _WorkflowLimit as limit:
            return _WorkflowOutcome(last_reviewed, usage, limit.reason, tuple(warnings))
        return _WorkflowOutcome(last_reviewed, usage, StopReason.ROUND_LIMIT, tuple(warnings))

    def _same_candidate_content(self, before: SuggestionIdea, after: SuggestionIdea) -> bool:
        # Compares meaningful candidate fields while ignoring generated identity and handoff data.
        ignored = {"id", "revision", "rank", "review_summary", "handoff"}
        before_values = before.model_dump(mode="json", exclude=ignored)
        after_values = after.model_dump(mode="json", exclude=ignored)
        return before_values == after_values

    async def _generate(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        count: int,
        started: float,
        usage: dict[str, int],
    ) -> SuggestionCandidateBatch:
        context = self._context_bridge.generator(request, categories)
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
                usage,
                "generation",
            ),
        )

    async def _critique(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        ideas: tuple[SuggestionIdea, ...],
        started: float,
        usage: dict[str, int],
    ) -> SuggestionCritiqueArtifact:
        context = self._context_bridge.critic(request, categories, ideas)
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
                usage,
                "critique",
            ),
        )

    async def _revise(
        self,
        request: SuggestionRequest,
        sdk: Any,
        categories: tuple[str, ...],
        current: tuple[SuggestionIdea, ...],
        revisions: tuple[tuple[SuggestionIdea, SuggestionCritique], ...],
        started: float,
        usage: dict[str, int],
    ) -> tuple[SuggestionIdea, ...]:
        context = self._context_bridge.revision(request, categories, revisions)
        prompt = self._prompts.revision_turn(request.goal, len(revisions))
        batch = await self._call_agent(
            sdk,
            "generator",
            self._prompts.revision_system(),
            prompt,
            context,
            None,
            SuggestionCandidateBatch,
            request,
            started,
            usage,
            "revision",
        )
        by_id = {idea.id: (idea, critique) for idea, critique in revisions}
        revised: list[SuggestionIdea] = []
        seen_ids: set[str] = set()
        for draft in batch.ideas:
            idea_id = draft.idea_id
            if idea_id is None:
                raise ValueError("revision output must preserve the candidate id")
            if idea_id in seen_ids:
                raise ValueError("revision output repeated a candidate id")
            seen_ids.add(idea_id)
            if idea_id not in by_id:
                raise ValueError("revision output referenced an unknown candidate id")
            original, critique = by_id[idea_id]
            values = draft.model_dump(exclude={"idea_id"})
            for field_name in critique.preserve:
                if hasattr(original, field_name) and field_name in values:
                    values[field_name] = getattr(original, field_name)
            revised_draft = SuggestionDraft.model_validate(values)
            revised.append(
                self._idea_from_draft(
                    revised_draft,
                    request,
                    idea_id,
                    original.revision + 1,
                    original.rank,
                    critique.review_summary,
                )
            )
        by_revision_id = {idea.id: idea for idea in revised}
        return tuple(by_revision_id[idea.id] for idea, _ in revisions if idea.id in by_revision_id)

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
                reply = await agent.arun(
                    sdk.run_input(SuggestionTextInput(prompt, request.attachments))
                )
            else:
                async with asyncio.timeout(remaining):
                    reply = await agent.arun(
                        sdk.run_input(SuggestionTextInput(prompt, request.attachments))
                    )
        except TimeoutError as error:
            raise _WorkflowLimit(StopReason.TIME_LIMIT) from error
        self._record_usage(reply, usage, phase)
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

    def _review(
        self, ideas: tuple[SuggestionIdea, ...], artifact: SuggestionCritiqueArtifact
    ) -> tuple[tuple[SuggestionIdea, ...], tuple[tuple[SuggestionIdea, SuggestionCritique], ...]]:
        critiques = {item.idea_id: item for item in artifact.critiques}
        if set(critiques) != {idea.id for idea in ideas} or len(critiques) != len(
            artifact.critiques
        ):
            raise ValueError("critic artifact must contain exactly one review for every candidate")
        kept: list[SuggestionIdea] = []
        revisions: list[tuple[SuggestionIdea, SuggestionCritique]] = []
        for idea in ideas:
            critique = critiques[idea.id]
            hard_reject = (
                critique.constraint_hit is not CritiqueConstraint.NONE
                or critique.evidence_check is CritiqueEvidenceCheck.CONTRADICTS
                or (
                    critique.verdict is CritiqueVerdict.REJECT
                    and critique.confidence is not CritiqueConfidence.LOW
                )
            )
            if critique.duplicate_of and critique.duplicate_of != idea.id:
                continue
            if hard_reject:
                continue
            needs_revision = (
                critique.verdict is CritiqueVerdict.REVISE
                or critique.evidence_check is CritiqueEvidenceCheck.MISSING
                or (
                    critique.verdict is CritiqueVerdict.REJECT
                    and critique.confidence is CritiqueConfidence.LOW
                )
            )
            if needs_revision:
                revisions.append((idea, critique))
                continue
            if critique.verdict is CritiqueVerdict.KEEP:
                kept.append(idea.model_copy(update={"review_summary": critique.review_summary}))
        return tuple(kept), tuple(revisions)

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

    def _merge_reviewed(
        self, previous: tuple[SuggestionIdea, ...], current: tuple[SuggestionIdea, ...]
    ) -> tuple[SuggestionIdea, ...]:
        # Carries kept candidates across a revision round without changing stable order.
        merged = {idea.id: idea for idea in previous}
        merged.update({idea.id: idea for idea in current})
        return tuple(merged.values())

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
            category_coverage=self._selection.coverage(ideas),
            missing_context=missing,
            warnings=tuple(dict.fromkeys(warnings)),
            usage=outcome.usage,
            stop_reason=outcome.stop_reason,
            prompt_version=request.prompt_version,
        )


__all__ = ["SuggestionService"]
