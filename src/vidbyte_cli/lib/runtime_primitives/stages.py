"""Runs caller-defined stages with one fresh Codex agent per stage attempt.

The SDK owns transport and thread identity. This adapter owns stage fan-out, sequential
handoff through the previous reply, and rejection of incomplete results. Every stage
setting arrives here already validated as a CLI enum or a settings-checked value, so this
module converts rather than parses: the closed value sets are enforced at the command
layer where Click can reject a bad word before the wallet is ever touched.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import (
    StageSpec,
    StagesResult,
    StagesSettings,
    StageStepResult,
)
from ..constants.runtime import StagesCodexConfig as CodexConfig
from ..constants.runtime import StagesLimit, StagesProgress
from ..errors.failures import StagesHostFailed, StagesSettingsInvalid

if TYPE_CHECKING:
    from vidbyte.agents.codex import CodexHarnessAgent
    from vidbyte.agents.types import AgentMessage
    from vidbyte.lib.dataclasses.codex import CodexHarnessAgentSettings


class StagesCodexSession:
    """One invocation's environment and lazy per-stage SDK agents."""

    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None:
        # Construction stays free of SDK imports so help never needs Codex.
        self._environment = dict(environment)
        self._progress = progress
        self._executable = ""
        self._working_directory = ""
        self._prepared = False

    def prepare(self, plan: Plan, settings: StagesSettings) -> None:
        # Records launch paths without starting any model turn, so every failure the
        # caller can cause is still ahead of payment. Agents are built lazily per
        # attempt because a failed attempt may hold broken transport state.
        from vidbyte.agents.codex import CodexHarnessAgent  # noqa: F401

        _ = settings
        self._executable = str(plan.executable)
        self._working_directory = str(plan.working_directory)
        self._prepared = True

    def run(self, plan: Plan, settings: StagesSettings, admission_id: str) -> StagesResult:
        # Dispatches to the chosen topology behind one guarded entry.
        from vidbyte.lib.errors import CodexAgentError

        if not self._prepared:
            raise StagesHostFailed()
        try:
            return asyncio.run(self._run(plan, settings, admission_id))
        except StagesHostFailed:
            raise
        except StagesSettingsInvalid:
            raise
        except (CodexAgentError, TimeoutError) as error:
            raise StagesHostFailed() from error

    async def _run(self, plan: Plan, settings: StagesSettings, admission_id: str) -> StagesResult:
        # Sequential threads prior output; parallel fans out independently.
        if settings.parallel:
            return await self._run_parallel(plan, settings, admission_id)
        return await self._run_sequential(plan, settings, admission_id)

    async def _run_sequential(
        self, plan: Plan, settings: StagesSettings, admission_id: str
    ) -> StagesResult:
        # Awaits each stage before starting the next one, keeping the completed prefix
        # when stop_on_error halts the run at the first exhausted stage.
        texts: list[str] = []
        steps: list[StageStepResult] = []
        completed = 0
        failed = 0
        previous = plan.task
        self._progress(StagesProgress.STAGE_STARTING)
        for index, spec in enumerate(settings.stages):
            prompt = spec.prompt.replace("{{previous}}", previous)
            outcome = await self._run_stage(plan, spec, index, prompt, settings)
            if outcome is None:
                failed += 1
                steps.append(self._failed_step(spec, index, settings))
                texts.append(f"Stage {index + 1} failed.")
                if settings.stop_on_error:
                    break
                continue
            completed += 1
            texts.append(outcome[0])
            steps.append(self._completed_step(spec, index, outcome[1], outcome[2], outcome[3]))
            previous = outcome[0]
            self._progress(StagesProgress.STAGE_COMPLETE)
        self._progress(StagesProgress.COMPLETE)
        return self._result(admission_id, completed, failed, steps, texts)

    async def _run_parallel(
        self, plan: Plan, settings: StagesSettings, admission_id: str
    ) -> StagesResult:
        # Starts every stage at once; stages must not depend on each other. Each stage
        # still retries on its own, and failures are recorded with placeholders so
        # indices stay aligned with the requested order.
        prompts = [spec.prompt.replace("{{previous}}", plan.task) for spec in settings.stages]
        outcomes = await asyncio.gather(
            *[
                self._run_stage(plan, spec, index, prompt, settings)
                for index, (spec, prompt) in enumerate(zip(settings.stages, prompts, strict=True))
            ]
        )
        texts: list[str] = []
        steps: list[StageStepResult] = []
        completed = 0
        failed = 0
        for index, (spec, outcome) in enumerate(zip(settings.stages, outcomes, strict=True)):
            if outcome is None:
                failed += 1
                steps.append(self._failed_step(spec, index, settings))
                texts.append(f"Stage {index + 1} failed.")
                continue
            completed += 1
            texts.append(outcome[0])
            steps.append(self._completed_step(spec, index, outcome[1], outcome[2], outcome[3]))
        self._progress(StagesProgress.COMPLETE)
        return self._result(admission_id, completed, failed, steps, texts)

    async def _run_stage(
        self, plan: Plan, spec: StageSpec, index: int, prompt: str, settings: StagesSettings
    ) -> tuple[str, str, int, int] | None:
        # One stage start to finish. Every attempt builds its own agent and sends the
        # same prompt, so a retry recovers from a dead host rather than from a stage
        # the agent understood but could not do. Returns text, thread id, attempts,
        # and duration, or None when every attempt is exhausted.
        from vidbyte.lib.errors import CodexAgentError

        _ = index
        started = time.perf_counter()
        attempts = 0
        for attempt in range(settings.max_retries_per_stage + 1):
            attempts = attempt + 1
            if attempt > 0:
                self._progress(StagesProgress.STAGE_RETRYING)
                await asyncio.sleep(self._backoff_seconds(attempt - 1))
            try:
                agent = self._build_agent(plan, spec)
                reply = await self._turn(agent, spec, prompt)
                thread = self._thread_id(reply)
                text = self._completed_text(reply)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return (text, thread, attempts, elapsed_ms)
            except (asyncio.CancelledError, KeyboardInterrupt):
                # Cancellation is never a host failure and never retries.
                raise
            except (StagesSettingsInvalid, ValueError):
                # Fatal caller content fails fast instead of burning retries.
                raise
            except (TimeoutError, ConnectionError, StagesHostFailed, CodexAgentError):
                # Transport and host failures retry with backoff at the loop top.
                continue
        return None

    def _backoff_seconds(self, retry_index: int) -> float:
        # Gives a recovering host room: 2s, 8s, 32s plus up to 1s of jitter so
        # concurrent stages do not retry at the same instant.
        return 2.0 * (4.0**retry_index) + random.uniform(0.0, 1.0)

    def _build_agent(self, plan: Plan, spec: StageSpec) -> CodexHarnessAgent:
        # Constructs a fresh agent so threads never leak across stages or attempts.
        from vidbyte.agents.codex import CodexHarnessAgent

        return CodexHarnessAgent(self._to_settings(plan, spec))

    async def _turn(self, agent: CodexHarnessAgent, spec: StageSpec, prompt: str) -> AgentMessage:
        # Timeout cancels arun so the SDK client unwinds before continuing.
        from vidbyte.lib.dataclasses.codex import (
            CodexMentionInput,
            CodexRunInput,
            CodexSkillInput,
            CodexTextInput,
        )

        items: list[Any] = [CodexTextInput(prompt)]
        if spec.image.strip():
            items.append(self._image_item(spec.image.strip()))
        if spec.skill.strip():
            name, _, path = spec.skill.partition("=")
            items.append(CodexSkillInput(name.strip(), path.strip()))
        if spec.mention.strip():
            name, _, path = spec.mention.partition("=")
            items.append(CodexMentionInput(name.strip(), path.strip()))
        run_input = CodexRunInput(items=tuple(items))
        async with asyncio.timeout(StagesLimit.TURN_TIMEOUT_SECONDS):
            return await agent.arun(run_input)

    def _image_item(self, image: str) -> Any:
        # Remote URLs and local paths are different SDK items with no shared shape.
        from vidbyte.lib.dataclasses.codex import CodexImageInput, CodexLocalImageInput

        if image.lower().startswith(("https://", "http://", "data:")):
            return CodexImageInput(image)
        return CodexLocalImageInput(image)

    def _completed_text(self, reply: AgentMessage) -> str:
        # Rejects incomplete replies without exposing model content in errors.
        data = reply.codex
        if data is None or data.status != "completed" or not data.final_response:
            raise StagesHostFailed()
        return str(reply.content)

    def _thread_id(self, reply: AgentMessage) -> str:
        # Requires a stable thread identity for per-step accounting.
        data = reply.codex
        thread = str(data.thread_id) if data is not None else ""
        if not thread.strip():
            raise StagesHostFailed()
        return thread

    def _completed_step(
        self, spec: StageSpec, index: int, thread: str, attempts: int, duration_ms: int
    ) -> StageStepResult:
        # Records one successful stage with its identity and attempt accounting.
        return StageStepResult(
            index=index,
            name=spec.name,
            status="completed",
            thread_id=thread,
            attempts=attempts,
            duration_ms=duration_ms,
        )

    def _failed_step(
        self, spec: StageSpec, index: int, settings: StagesSettings
    ) -> StageStepResult:
        # Records one exhausted stage with a static placeholder thread identity.
        return StageStepResult(
            index=index,
            name=spec.name,
            status="failed",
            thread_id=f"stage-{index + 1}-failed",
            attempts=settings.max_retries_per_stage + 1,
            duration_ms=0,
        )

    def _result(
        self,
        admission_id: str,
        completed: int,
        failed: int,
        steps: list[StageStepResult],
        texts: list[str],
    ) -> StagesResult:
        # Joins per-stage texts into the run-level text, keeping indices aligned even
        # across failures so a later stage never reads the wrong predecessor.
        text = texts[-1] if texts else ""
        if any(step.status == "failed" for step in steps):
            text = "\n\n".join(texts)
        return StagesResult(
            admission_id=admission_id,
            completed=completed,
            failed=failed,
            steps=tuple(steps),
            stage_texts=tuple(texts),
            text=text,
        )

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
            schema: dict[str, Any] | None = None
            if spec.output_schema.strip():
                parsed: Any = json.loads(spec.output_schema)
                if not isinstance(parsed, dict):
                    raise StagesSettingsInvalid()
                schema = parsed
            return CodexHarnessAgentSettings(
                name=spec.name,
                system_prompt=spec.system_prompt,
                additional_context=spec.additional_context,
                output_schema=schema,
                codex=CodexAgentSettings(client=client, thread=thread, turn=turn),
            )
        except StagesSettingsInvalid:
            raise
        except ValueError as error:
            raise StagesSettingsInvalid() from error
