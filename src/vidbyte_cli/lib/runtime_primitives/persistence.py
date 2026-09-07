"""Runs a fixed continuation loop through the SDK's CodexHarnessAgent.

The SDK owns transport and thread resumption. This adapter owns exact task input,
turn limits, progress, and rejection of incomplete or changed-thread results.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from importlib.resources import files
from typing import TYPE_CHECKING

from ...types.runtime import PersistenceResult, PersistenceSettings
from ...types.runtime import RuntimeLaunchPlan as Plan
from ..constants.runtime import PersistenceCodexConfig, PersistenceLimit
from ..constants.runtime import PersistenceProgress as Progress
from ..errors.failures import PersistenceHostFailed

if TYPE_CHECKING:
    from vidbyte.agents.codex import CodexHarnessAgent
    from vidbyte.agents.types import AgentMessage


class PersistentCodexSession:
    """One invocation's environment and SDK agent, prepared before paid admission."""

    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None:
        self._environment = dict(environment)
        self._progress = progress
        self._agent: CodexHarnessAgent | None = None

    def prepare(self, plan: Plan) -> None:
        # Construction validates local SDK settings without starting a paid model turn.
        from vidbyte.agents.codex import CodexHarnessAgent
        from vidbyte.lib.dataclasses.codex import (
            CodexAgentSettings,
            CodexClientSettings,
            CodexHarnessAgentSettings,
            CodexThreadSettings,
        )
        from vidbyte.lib.enums.codex import CodexSandbox

        client = CodexClientSettings(
            codex_bin=str(plan.executable),
            cwd=str(plan.working_directory),
            env=self._environment,
            config_overrides=tuple(setting.value for setting in PersistenceCodexConfig),
        )
        self._agent = CodexHarnessAgent(
            CodexHarnessAgentSettings(
                name="persistence",
                system_prompt=self._prompt("persistence_system.md"),
                codex=CodexAgentSettings(
                    client=client,
                    thread=CodexThreadSettings(sandbox=CodexSandbox.WORKSPACE_WRITE),
                ),
            )
        )

    def run(self, plan: Plan, settings: PersistenceSettings) -> PersistenceResult:
        from vidbyte.lib.errors import CodexAgentError

        if self._agent is None:
            raise PersistenceHostFailed()
        try:
            return asyncio.run(self._run(plan, settings))
        except (CodexAgentError, TimeoutError) as error:
            # SDK diagnostics may carry task content; only the static CLI failure is public.
            raise PersistenceHostFailed() from error

    async def _run(self, plan: Plan, settings: PersistenceSettings) -> PersistenceResult:
        continuation = self._prompt("continuation.md").replace("{{original_task}}", plan.task)
        self._progress(Progress.STARTING)
        reply = await self._turn(plan.task)
        session_id = self._session_id(reply, "")
        self._progress(Progress.INITIAL_COMPLETE)
        # The chosen strength, not a model's claim of completion, controls the loop.
        for index in range(settings.repeat_count):
            self._progress(self._continuation_progress(index, settings.repeat_count))
            reply = await self._turn(continuation)
            self._session_id(reply, session_id)
        self._progress(Progress.COMPLETE)
        return PersistenceResult(
            session_id=session_id, continuation_turns=settings.repeat_count, text=reply.content
        )

    async def _turn(self, prompt: str) -> AgentMessage:
        from vidbyte.lib.dataclasses.codex import CodexRunInput

        if self._agent is None:
            raise PersistenceHostFailed()
        # Timeout cancels arun so the SDK's async client unwinds before the loop can continue.
        async with asyncio.timeout(PersistenceLimit.TURN_TIMEOUT_SECONDS):
            return await self._agent.arun(CodexRunInput.text(prompt))

    def _session_id(self, reply: AgentMessage, previous: str) -> str:
        data = reply.codex
        if data is None or data.status != "completed" or not data.final_response:
            raise PersistenceHostFailed()
        if not data.thread_id.strip() or (previous and data.thread_id != previous):
            raise PersistenceHostFailed()
        if self._agent is None or self._agent.thread_id != data.thread_id:
            raise PersistenceHostFailed()
        return data.thread_id

    def _continuation_progress(self, index: int, count: int) -> Progress:
        if index == count - 1:
            return Progress.FINAL
        if index * 3 < count:
            return Progress.EARLY
        if index * 3 < count * 2:
            return Progress.MIDDLE
        return Progress.LATE

    def _prompt(self, name: str) -> str:
        return files(__package__).joinpath(name).read_text(encoding="utf-8")
