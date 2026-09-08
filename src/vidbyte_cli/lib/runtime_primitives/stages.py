"""Runs caller-defined stages with one fresh Codex agent per stage.

The SDK owns transport and thread identity. This adapter owns stage fan-out,
sequential handoff through the previous reply, and rejection of incomplete
or cross-stage-reused results.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import StageSpec, StagesResult, StagesSettings
from ..constants.runtime import PersistenceCodexConfig as CodexConfig
from ..constants.runtime import StagesLimit, StagesProgress
from ..errors.failures import StagesHostFailed, StagesSettingsInvalid

if TYPE_CHECKING:
    from vidbyte.agents.codex import CodexHarnessAgent
    from vidbyte.agents.types import AgentMessage
    from vidbyte.lib.dataclasses.codex import CodexHarnessAgentSettings
    from vidbyte.lib.enums.codex import (
        CodexApprovalMode,
        CodexPersonality,
        CodexReasoningEffort,
        CodexReasoningSummary,
        CodexSandbox,
    )


class StagesFile:
    """Loads and describes the offline stages document consumed by run."""

    def load(self, path: str) -> StagesSettings:
        # Parses JSON and validates it as frozen stages settings.
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise StagesSettingsInvalid() from error
        try:
            return StagesSettings.model_validate(raw)
        except ValueError as error:
            raise StagesSettingsInvalid() from error

    def build_settings(self, specs: list[StageSpec], parallel: bool) -> StagesSettings:
        # Validates caller-built specs through the same frozen contract.
        try:
            return StagesSettings(stages=tuple(specs), parallel=parallel)
        except ValueError as error:
            raise StagesSettingsInvalid() from error

    def describe(self) -> str:
        # Returns agent-facing help naming every tunable and its mapping.
        return (
            "Each stages[] entry maps to one fresh CodexHarnessAgent: "
            "name/system_prompt/prompt (required text), model/effort/"
            "summary/sandbox/approval/personality (native Codex controls), "
            "additional_context (turn-scoped context). "
            "parallel=false runs in order with {{previous}} as prior output; "
            "parallel=true runs all stages at once with asyncio.gather."
        )


class StagesCodexSession:
    """One invocation's environment and per-stage SDK agents."""

    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None:
        # Construction stays free of SDK imports so help never needs Codex.
        self._environment = dict(environment)
        self._progress = progress
        self._agents: list[CodexHarnessAgent] = []

    def prepare(self, plan: Plan, settings: StagesSettings) -> None:
        # Builds one validated agent per stage without starting any model turn.
        from vidbyte.agents.codex import CodexHarnessAgent

        self._agents = [
            CodexHarnessAgent(self._to_settings(plan, spec)) for spec in settings.stages
        ]

    def run(self, plan: Plan, settings: StagesSettings) -> StagesResult:
        # Dispatches to the chosen topology behind one guarded entry.
        from vidbyte.lib.errors import CodexAgentError

        if not self._agents or len(self._agents) != len(settings.stages):
            raise StagesHostFailed()
        try:
            return asyncio.run(self._run(plan, settings))
        except (CodexAgentError, TimeoutError) as error:
            raise StagesHostFailed() from error

    async def _run(self, plan: Plan, settings: StagesSettings) -> StagesResult:
        # Sequential threads prior output; parallel fans out independently.
        if settings.parallel:
            return await self._run_parallel(plan, settings)
        return await self._run_sequential(plan, settings)

    async def _run_sequential(self, plan: Plan, settings: StagesSettings) -> StagesResult:
        # Awaits each stage before starting the next one.
        texts: list[str] = []
        previous = plan.task
        for index, agent in enumerate(self._agents):
            self._progress(StagesProgress.STAGE_STARTING)
            prompt = settings.stages[index].prompt.replace("{{previous}}", previous)
            reply = await self._turn(agent, prompt)
            text = self._completed_text(reply, index)
            texts.append(text)
            previous = text
            self._progress(StagesProgress.STAGE_COMPLETE)
        self._progress(StagesProgress.COMPLETE)
        return StagesResult(stage_texts=tuple(texts), text=texts[-1])

    async def _run_parallel(self, plan: Plan, settings: StagesSettings) -> StagesResult:
        # Starts every stage at once; stages must not depend on each other.
        prompts = [spec.prompt.replace("{{previous}}", plan.task) for spec in settings.stages]
        pairs = zip(self._agents, prompts, strict=True)
        replies = await asyncio.gather(*[self._turn(agent, prompt) for agent, prompt in pairs])
        texts = [self._completed_text(reply, i) for i, reply in enumerate(replies)]
        self._progress(StagesProgress.COMPLETE)
        return StagesResult(stage_texts=tuple(texts), text="\n\n".join(texts))

    async def _turn(self, agent: CodexHarnessAgent, prompt: str) -> AgentMessage:
        # Timeout cancels arun so the SDK client unwinds before continuing.
        from vidbyte.lib.dataclasses.codex import CodexRunInput

        async with asyncio.timeout(StagesLimit.TURN_TIMEOUT_SECONDS):
            return await agent.arun(CodexRunInput.text(prompt))

    def _completed_text(self, reply: AgentMessage, index: int) -> str:
        # Rejects incomplete replies and proves which stage produced the text.
        _ = index
        data = reply.codex
        if data is None or data.status != "completed" or not data.final_response:
            raise StagesHostFailed()
        if not data.thread_id.strip():
            raise StagesHostFailed()
        return reply.content

    def _to_settings(self, plan: Plan, spec: StageSpec) -> CodexHarnessAgentSettings:
        # Translates one stage spec to validated harness agent settings.
        from vidbyte.lib.dataclasses.codex import (
            CodexAgentSettings,
            CodexClientSettings,
            CodexHarnessAgentSettings,
            CodexThreadSettings,
            CodexTurnSettings,
        )

        client = CodexClientSettings(
            codex_bin=str(plan.executable),
            cwd=str(plan.working_directory),
            env=self._environment,
            config_overrides=tuple(s.value for s in CodexConfig),
        )
        thread = CodexThreadSettings(
            model=spec.model,
            sandbox=self._sandbox(spec.sandbox),
            approval_mode=self._approval(spec.approval),
            personality=self._personality(spec.personality),
        )
        turn = CodexTurnSettings(
            model=spec.model,
            effort=self._effort(spec.effort),
            summary=self._summary(spec.summary),
            sandbox=self._sandbox(spec.sandbox),
            approval_mode=self._approval(spec.approval),
            personality=self._personality(spec.personality),
        )
        try:
            return CodexHarnessAgentSettings(
                name=spec.name,
                system_prompt=spec.system_prompt,
                additional_context=spec.additional_context,
                codex=CodexAgentSettings(client=client, thread=thread, turn=turn),
            )
        except ValueError as error:
            raise StagesSettingsInvalid() from error

    def _sandbox(self, value: str) -> CodexSandbox:
        # Maps CLI sandbox words to the SDK enum without accepting aliases.
        from vidbyte.lib.enums.codex import CodexSandbox

        mapping: dict[str, CodexSandbox] = {
            "read-only": CodexSandbox.READ_ONLY,
            "workspace-write": CodexSandbox.WORKSPACE_WRITE,
            "full-access": CodexSandbox.FULL_ACCESS,
        }
        try:
            return mapping[value.strip().lower()]
        except KeyError as error:
            raise StagesSettingsInvalid() from error

    def _effort(self, value: str) -> CodexReasoningEffort:
        # Maps CLI effort words to the SDK reasoning-effort enum.
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        mapping: dict[str, CodexReasoningEffort] = {
            "none": CodexReasoningEffort.NONE,
            "minimal": CodexReasoningEffort.MINIMAL,
            "low": CodexReasoningEffort.LOW,
            "medium": CodexReasoningEffort.MEDIUM,
            "high": CodexReasoningEffort.HIGH,
            "xhigh": CodexReasoningEffort.XHIGH,
        }
        try:
            return mapping[value.strip().lower()]
        except KeyError as error:
            raise StagesSettingsInvalid() from error

    def _summary(self, value: str) -> CodexReasoningSummary:
        # Maps CLI summary words to the SDK reasoning-summary enum.
        from vidbyte.lib.enums.codex import CodexReasoningSummary

        mapping: dict[str, CodexReasoningSummary] = {
            "none": CodexReasoningSummary.NONE,
            "auto": CodexReasoningSummary.AUTO,
            "concise": CodexReasoningSummary.CONCISE,
            "detailed": CodexReasoningSummary.DETAILED,
        }
        try:
            return mapping[value.strip().lower()]
        except KeyError as error:
            raise StagesSettingsInvalid() from error

    def _approval(self, value: str) -> CodexApprovalMode:
        # Maps CLI approval words to the SDK approval-mode enum.
        from vidbyte.lib.enums.codex import CodexApprovalMode

        mapping: dict[str, CodexApprovalMode] = {
            "auto_review": CodexApprovalMode.AUTO_REVIEW,
            "deny_all": CodexApprovalMode.DENY_ALL,
        }
        try:
            return mapping[value.strip().lower()]
        except KeyError as error:
            raise StagesSettingsInvalid() from error

    def _personality(self, value: str) -> CodexPersonality:
        # Maps CLI personality words to the SDK personality enum.
        from vidbyte.lib.enums.codex import CodexPersonality

        mapping: dict[str, CodexPersonality] = {
            "none": CodexPersonality.NONE,
            "friendly": CodexPersonality.FRIENDLY,
            "pragmatic": CodexPersonality.PRAGMATIC,
        }
        try:
            return mapping[value.strip().lower()]
        except KeyError as error:
            raise StagesSettingsInvalid() from error
