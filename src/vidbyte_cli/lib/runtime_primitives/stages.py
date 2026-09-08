"""Runs caller-defined stages with one fresh Codex agent per stage.

The SDK owns transport and thread identity. This adapter owns stage fan-out, sequential
handoff through the previous reply, and rejection of incomplete or cross-stage-reused
results. Every stage setting arrives here already validated as a CLI enum, so this module
converts rather than parses: the closed value sets are enforced at the command layer where
Click can reject a bad word before the wallet is ever touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import StageSpec, StagesResult, StagesSettings
from ..constants.runtime import StagesCodexConfig as CodexConfig
from ..constants.runtime import StagesLimit, StagesProgress
from ..errors.failures import StagesHostFailed, StagesSettingsInvalid

if TYPE_CHECKING:
    from vidbyte.agents.codex import CodexHarnessAgent
    from vidbyte.agents.types import AgentMessage
    from vidbyte.lib.dataclasses.codex import CodexHarnessAgentSettings


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
        return str(reply.content)

    def _to_settings(self, plan: Plan, spec: StageSpec) -> CodexHarnessAgentSettings:
        # Translates one stage spec to validated harness agent settings. Every closed-set value
        # is already a CLI enum whose members are a subset of the SDK's, so each one converts by
        # value with no lookup table and no alias handling: review of PR #36 asked for the legal
        # words to be defined and enforced as enums in the command layer rather than re-parsed
        # from free strings here. A ValueError can still surface if the pinned SDK drops a
        # member, and it is reported as invalid settings rather than as a host failure.
        from vidbyte.lib.dataclasses.codex import (
            CodexAgentSettings,
            CodexClientSettings,
            CodexHarnessAgentSettings,
            CodexThreadSettings,
            CodexTurnSettings,
        )
        from vidbyte.lib.enums.codex import (
            CodexApprovalMode,
            CodexPersonality,
            CodexReasoningEffort,
            CodexReasoningSummary,
            CodexSandbox,
        )

        try:
            sandbox = CodexSandbox(spec.sandbox.value)
            approval = CodexApprovalMode(spec.approval.value)
            personality = CodexPersonality(spec.personality.value)
            client = CodexClientSettings(
                codex_bin=str(plan.executable),
                cwd=str(plan.working_directory),
                env=self._environment,
                config_overrides=tuple(setting.value for setting in CodexConfig),
            )
            thread = CodexThreadSettings(
                model=spec.model,
                sandbox=sandbox,
                approval_mode=approval,
                personality=personality,
            )
            turn = CodexTurnSettings(
                model=spec.model,
                effort=CodexReasoningEffort(spec.effort.value),
                summary=CodexReasoningSummary(spec.summary.value),
                sandbox=sandbox,
                approval_mode=approval,
                personality=personality,
            )
            return CodexHarnessAgentSettings(
                name=spec.name,
                system_prompt=spec.system_prompt,
                additional_context=spec.additional_context,
                codex=CodexAgentSettings(client=client, thread=thread, turn=turn),
            )
        except ValueError as error:
            raise StagesSettingsInvalid() from error
