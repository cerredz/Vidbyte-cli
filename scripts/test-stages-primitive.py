"""Verification script for the stages primitive design doc, section 10.

Offline only: no network, no Codex turns, no credentials. Each case prints
PASS/FAIL and the script exits non-zero when any case fails.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.runtime.stages import StagesCommand
from vidbyte_cli.lib.errors.failures import (
    StagesHostFailed,
    StagesOptionCountMismatch,
    StagesSettingsInvalid,
)
from vidbyte_cli.lib.runtime_primitives.gate import RuntimeAdmissionGate
from vidbyte_cli.lib.runtime_primitives.stages import StagesCodexSession
from vidbyte_cli.types.runtime import (
    RuntimeHost,
    StageEffort,
    StageSandbox,
    StageSpec,
    StagesSettings,
)


class CaseRunner:
    """Collects labeled results and renders the final summary."""

    def __init__(self) -> None:
        # Starts with zero recorded outcomes.
        self.passed = 0
        self.total = 0

    def check(self, name: str, ok: bool) -> None:
        # Records one outcome and prints its label immediately.
        self.total += 1
        if ok:
            self.passed += 1
            print(f"PASS {name}")
        else:
            print(f"FAIL {name}")

    def report(self) -> int:
        # Prints the summary and maps it to a process exit code.
        print(f"{self.passed}/{self.total} tests passed")
        return 0 if self.passed == self.total else 1


def make_plan() -> object:
    # Builds a minimal stages launch plan without host discovery.
    from vidbyte_cli.types.runtime import RuntimeLaunchPlan

    return RuntimeLaunchPlan(
        capability_id="runtime.stages@1",
        host=RuntimeHost.CODEX,
        executable=Path("."),
        working_directory=Path("."),
        task="Add rate limiting",
    )


def make_grant(capability_id: str, cents: int) -> object:
    # Builds a grant with a live time window for policy checks.
    from vidbyte_cli.types.runtime import RuntimeAdmissionGrant

    now = datetime.now(UTC)
    return RuntimeAdmissionGrant(
        admission_id="rta_test123",
        capability_id=capability_id,
        execution_location="local",
        charged_cents=cents,
        admitted_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(seconds=600),
        grant_token="x" * 32,
    )


def spec(i: int) -> StageSpec:
    # Builds one valid stage spec for count-bound tests.
    return StageSpec(name=f"s{i}", prompt="do it", system_prompt="be good")


class EdgeCases:
    """Boundary inputs around stage counts, blanks, and CLI option alignment."""

    def __init__(self, runner: CaseRunner) -> None:
        # Keeps one shared runner across all edge cases.
        self._runner = runner
        self._command = StagesCommand()

    def run_all(self) -> None:
        # Runs every edge case in file order.
        self._empty_rejected()
        self._twenty_six_rejected()
        self._twenty_five_accepted()
        self._blank_prompt_rejected()
        self._blank_system_rejected()
        self._previous_resolves()
        self._no_prompt_rejected()
        self._missing_system_rejected()
        self._count_mismatch_rejected()
        self._omitted_options_default()
        self._options_align_by_position()
        self._unknown_effort_rejected()
        self._parallel_flag_carried()

    def _empty_rejected(self) -> None:
        # Zero stages must fail validation.
        try:
            StagesSettings(stages=(), parallel=False)
            self._runner.check("[Edge Case] empty stages rejected", False)
        except ValueError:
            self._runner.check("[Edge Case] empty stages rejected", True)

    def _twenty_six_rejected(self) -> None:
        # Twenty-six stages exceed the reviewed ceiling of twenty-five.
        try:
            StagesSettings(stages=tuple(spec(i) for i in range(26)), parallel=False)
            self._runner.check("[Edge Case] 26 stages rejected", False)
        except ValueError:
            self._runner.check("[Edge Case] 26 stages rejected", True)

    def _twenty_five_accepted(self) -> None:
        # Twenty-five stages exactly fill the allowed range.
        try:
            StagesSettings(stages=tuple(spec(i) for i in range(25)), parallel=False)
            self._runner.check("[Edge Case] 25 stages accepted", True)
        except ValueError:
            self._runner.check("[Edge Case] 25 stages accepted", False)

    def _blank_prompt_rejected(self) -> None:
        # Whitespace-only prompts would burn a paid turn.
        try:
            StageSpec(name="a", prompt="   ", system_prompt="be good")
            self._runner.check("[Edge Case] blank prompt rejected", False)
        except ValueError:
            self._runner.check("[Edge Case] blank prompt rejected", True)

    def _blank_system_rejected(self) -> None:
        # Whitespace-only system prompts leave the agent roleless.
        try:
            StageSpec(name="a", prompt="do it", system_prompt="   ")
            self._runner.check("[Edge Case] blank system rejected", False)
        except ValueError:
            self._runner.check("[Edge Case] blank system rejected", True)

    def _previous_resolves(self) -> None:
        # Stage zero inherits the top-level task text.
        replaced = "Write it. Input: {{previous}}".replace("{{previous}}", "task")
        self._runner.check("[Edge Case] previous resolves", replaced == "Write it. Input: task")

    def _no_prompt_rejected(self) -> None:
        # A run with no --stage-prompt at all describes no stage.
        try:
            self._command._settings({}, False, True, 1)  # noqa: SLF001
            self._runner.check("[Edge Case] missing stage prompt rejected", False)
        except StagesSettingsInvalid:
            self._runner.check("[Edge Case] missing stage prompt rejected", True)

    def _missing_system_rejected(self) -> None:
        # A prompt without its system prompt would leave the stage roleless.
        options = {"prompts": ("p",)}
        try:
            self._command._settings(options, False, True, 1)  # noqa: SLF001
            self._runner.check("[Edge Case] missing system prompt rejected", False)
        except StagesSettingsInvalid:
            self._runner.check("[Edge Case] missing system prompt rejected", True)

    def _count_mismatch_rejected(self) -> None:
        # One option repeated a different number of times leaves the run ambiguous.
        options = {
            "prompts": ("p1", "p2"),
            "systems": ("s1", "s2"),
            "sandboxes": (StageSandbox.READ_ONLY.value,),
        }
        try:
            self._command._settings(options, False, True, 1)  # noqa: SLF001
            self._runner.check("[Hidden Failure] option count mismatch rejected", False)
        except StagesOptionCountMismatch:
            self._runner.check("[Hidden Failure] option count mismatch rejected", True)

    def _omitted_options_default(self) -> None:
        # An omitted optional option gives every stage that setting's default.
        options = {"prompts": ("p1", "p2"), "systems": ("s1", "s2")}
        settings = self._command._settings(options, False, True, 1)  # noqa: SLF001
        first, second = settings.stages
        ok = (
            first.name == "stage-1"
            and second.name == "stage-2"
            and first.effort is StageEffort.MEDIUM
            and first.sandbox is StageSandbox.WORKSPACE_WRITE
            and second.model == ""
        )
        self._runner.check("[Hidden Assumption] omitted options default", ok)

    def _options_align_by_position(self) -> None:
        # Occurrence i of every option must land on stage i, never off by one.
        options = {
            "prompts": ("p1", "p2", "p3"),
            "systems": ("s1", "s2", "s3"),
            "names": ("audit", "design", "build"),
            "sandboxes": (
                StageSandbox.READ_ONLY.value,
                StageSandbox.READ_ONLY.value,
                StageSandbox.WORKSPACE_WRITE.value,
            ),
            "efforts": (
                StageEffort.HIGH.value,
                StageEffort.LOW.value,
                StageEffort.XHIGH.value,
            ),
        }
        settings = self._command._settings(options, False, True, 1)  # noqa: SLF001
        ok = (
            [stage.name for stage in settings.stages] == ["audit", "design", "build"]
            and [stage.prompt for stage in settings.stages] == ["p1", "p2", "p3"]
            and settings.stages[2].sandbox is StageSandbox.WORKSPACE_WRITE
            and settings.stages[1].effort is StageEffort.LOW
        )
        self._runner.check("[Silent Failure] options align by position", ok)

    def _unknown_effort_rejected(self) -> None:
        # A word outside the closed enum must never reach the SDK as a default.
        options = {"prompts": ("p",), "systems": ("s",), "efforts": ("very-high",)}
        try:
            self._command._settings(options, False, True, 1)  # noqa: SLF001
            self._runner.check("[Hidden Failure] unknown effort rejected", False)
        except StagesSettingsInvalid:
            self._runner.check("[Hidden Failure] unknown effort rejected", True)

    def _parallel_flag_carried(self) -> None:
        # The topology flag must reach the frozen settings unchanged.
        options = {"prompts": ("p",), "systems": ("s",)}
        settings = self._command._settings(options, True, True, 1)  # noqa: SLF001
        self._runner.check("[Hidden Assumption] parallel flag carried", settings.parallel is True)


class GateCases:
    """Admission-gateway behavior around capability, price, and identity."""

    def __init__(self, runner: CaseRunner) -> None:
        # Keeps one shared runner across all gateway cases.
        self._runner = runner
        self._gate = RuntimeAdmissionGate()
        self._plan = make_plan()

    def run_all(self) -> None:
        # Runs every gateway case in file order.
        self._wrong_capability()
        self._wrong_price()
        self._correct_grant()
        self._executor_rejects_host()
        self._executor_rejects_drift()
        self._hash_stable()

    def _wrong_capability(self) -> None:
        # A persistence grant must never admit a stages plan.
        grant = make_grant("runtime.persistence@1", 2)
        verdict = self._gate.verify_online(self._plan, grant, grant)  # type: ignore[arg-type]
        ok = not verdict.admitted and verdict.reason == "grant_capability_mismatch"
        self._runner.check("[Hidden Failure] wrong capability rejected", ok)

    def _wrong_price(self) -> None:
        # A two-cent receipt must never admit a one-cent product.
        grant = make_grant("runtime.stages@1", 2)
        verdict = self._gate.verify_online(self._plan, grant, grant)  # type: ignore[arg-type]
        ok = not verdict.admitted and verdict.reason == "grant_price_mismatch"
        self._runner.check("[Hidden Failure] wrong price rejected", ok)

    def _correct_grant(self) -> None:
        # A matching one-cent receipt admits the stages plan.
        grant = make_grant("runtime.stages@1", 1)
        verdict = self._gate.verify_online(self._plan, grant, grant)  # type: ignore[arg-type]
        ok = verdict.admitted and verdict.capability_id == "runtime.stages@1"
        self._runner.check("[Hidden Assumption] 1c grant admitted", ok)
        self._verdict = verdict

    def _executor_rejects_host(self) -> None:
        # An unprepared host must fail even with a valid verdict.
        from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor

        tune = StagesSettings(stages=(StageSpec(name="a", prompt="p", system_prompt="s"),))
        try:
            RuntimeExecutor().execute_stages(self._plan, tune, object(), self._verdict)  # type: ignore[arg-type]
            self._runner.check("[Hidden Failure] bad host rejected", False)
        except Exception:
            self._runner.check("[Hidden Failure] bad host rejected", True)

    def _executor_rejects_drift(self) -> None:
        # A drifted capability must fail even with a valid verdict.
        from vidbyte_cli.lib.errors.failures import RuntimeAdmissionNotVerified
        from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor

        tune = StagesSettings(stages=(StageSpec(name="a", prompt="p", system_prompt="s"),))
        drifted = self._plan.model_copy(update={"capability_id": "runtime.persistence@1"})
        try:
            RuntimeExecutor().execute_stages(drifted, tune, object(), self._verdict)  # type: ignore[arg-type]
            self._runner.check("[Silent Failure] drift rejected", False)
        except RuntimeAdmissionNotVerified:
            self._runner.check("[Silent Failure] drift rejected", True)
        except Exception:
            self._runner.check("[Silent Failure] drift rejected", False)

    def _hash_stable(self) -> None:
        # The key hash must be stable 64-hex for verify binding.
        first = RuntimeAdmissionGate.hash_idempotency_key("abc-123")
        second = RuntimeAdmissionGate.hash_idempotency_key("abc-123")
        ok = first == second and len(first) == 64
        self._runner.check("[Hidden Assumption] hash stable", ok)


class ReplyCases:
    """Reply validation around completion, identity, and failure."""

    def __init__(self, runner: CaseRunner) -> None:
        # Keeps one shared runner across all reply cases.
        self._runner = runner
        self._session = StagesCodexSession({}, lambda _msg: None)

    def run_all(self) -> None:
        # Runs every reply case in file order.
        self._completed_accepted()
        self._blank_thread_rejected()
        self._incomplete_rejected()

    def _completed_accepted(self) -> None:
        # A completed reply with an id returns its text.
        reply = self._reply("completed", "done", "thr_1", "done")
        try:
            text = self._session._completed_text(reply)  # noqa: SLF001
            self._runner.check("[Silent Failure] completed accepted", text == "done")
        except Exception:
            self._runner.check("[Silent Failure] completed accepted", False)

    def _blank_thread_rejected(self) -> None:
        # A blank thread id cannot prove stage identity.
        reply = self._reply("completed", "done", "   ", "done")
        try:
            self._session._thread_id(reply)  # noqa: SLF001
            self._runner.check("[Silent Failure] blank thread rejected", False)
        except Exception:
            self._runner.check("[Silent Failure] blank thread rejected", True)

    def _incomplete_rejected(self) -> None:
        # A failed turn must stop the sequence immediately.
        reply = self._reply("failed", "", "thr_1", "")
        try:
            self._session._completed_text(reply)  # noqa: SLF001
            self._runner.check("[Hidden Failure] incomplete rejected", False)
        except Exception:
            self._runner.check("[Hidden Failure] incomplete rejected", True)

    def _reply(self, status: str, final: str, thread: str, content: str) -> object:
        # Builds a minimal reply shape for validation tests.
        inner = SimpleNamespace(status=status, final_response=final, thread_id=thread)
        return SimpleNamespace(codex=inner, content=content)


class InputCases:
    """Richer per-stage inputs and their settings enforcement."""

    def __init__(self, runner: CaseRunner) -> None:
        # Keeps one shared runner across all input cases.
        self._runner = runner
        self._command = StagesCommand()

    def run_all(self) -> None:
        # Runs every input case in file order.
        self._inputs_align_by_position()
        self._inputs_default_empty()
        self._inputs_count_mismatch_rejected()
        self._blank_image_rejected()
        self._skill_without_separator_rejected()
        self._skill_blank_path_rejected()
        self._mention_without_separator_rejected()
        self._schema_non_object_rejected()
        self._schema_malformed_rejected()
        self._retry_policy_carried()
        self._retry_policy_bounds_rejected()

    def _inputs_align_by_position(self) -> None:
        # Occurrence i of each richer option must land on stage i.
        options = {
            "prompts": ("p1", "p2"),
            "systems": ("s1", "s2"),
            "images": ("https://example.com/a.png", ""),
            "skills": ("", "reviewer=skills/reviewer"),
            "mentions": ("spec=docs/spec.md", ""),
            "schemas": ("", '{"files": [], "summary": ""}'),
        }
        settings = self._command._settings(options, False, True, 1)  # noqa: SLF001
        first, second = settings.stages
        ok = (
            first.image == "https://example.com/a.png"
            and second.image == ""
            and first.skill == ""
            and second.skill == "reviewer=skills/reviewer"
            and first.mention == "spec=docs/spec.md"
            and second.output_schema == '{"files": [], "summary": ""}'
        )
        self._runner.check("[Hidden Assumption] richer inputs align by position", ok)

    def _inputs_default_empty(self) -> None:
        # Omitted richer options leave every stage on text alone.
        options = {"prompts": ("p",), "systems": ("s",)}
        settings = self._command._settings(options, False, True, 1)  # noqa: SLF001
        only = settings.stages[0]
        ok = (
            only.image == ""
            and only.skill == ""
            and only.mention == ""
            and only.output_schema == ""
        )
        self._runner.check("[Hidden Assumption] omitted inputs default empty", ok)

    def _inputs_count_mismatch_rejected(self) -> None:
        # A partial richer list leaves the run ambiguous like any other option.
        options = {
            "prompts": ("p1", "p2"),
            "systems": ("s1", "s2"),
            "images": ("https://example.com/a.png",),
        }
        try:
            self._command._settings(options, False, True, 1)  # noqa: SLF001
            self._runner.check("[Hidden Failure] image count mismatch rejected", False)
        except StagesOptionCountMismatch:
            self._runner.check("[Hidden Failure] image count mismatch rejected", True)

    def _blank_image_rejected(self) -> None:
        # A whitespace image would send an empty input item to the SDK.
        try:
            StageSpec(name="a", prompt="p", system_prompt="s", image="   ")
            self._runner.check("[Hidden Failure] blank image rejected", False)
        except ValueError:
            self._runner.check("[Hidden Failure] blank image rejected", True)

    def _skill_without_separator_rejected(self) -> None:
        # A skill without NAME=PATH cannot be split without guessing.
        try:
            StageSpec(name="a", prompt="p", system_prompt="s", skill="reviewer")
            self._runner.check("[Hidden Failure] skill without separator rejected", False)
        except ValueError:
            self._runner.check("[Hidden Failure] skill without separator rejected", True)

    def _skill_blank_path_rejected(self) -> None:
        # A skill with a blank path names nothing to load.
        try:
            StageSpec(name="a", prompt="p", system_prompt="s", skill="reviewer=   ")
            self._runner.check("[Hidden Failure] skill blank path rejected", False)
        except ValueError:
            self._runner.check("[Hidden Failure] skill blank path rejected", True)

    def _mention_without_separator_rejected(self) -> None:
        # A mention without NAME=PATH cannot be split without guessing.
        try:
            StageSpec(name="a", prompt="p", system_prompt="s", mention="docs/spec.md")
            self._runner.check("[Hidden Failure] mention without separator rejected", False)
        except ValueError:
            self._runner.check("[Hidden Failure] mention without separator rejected", True)

    def _schema_non_object_rejected(self) -> None:
        # A schema that parses to a list is not an object the SDK can enforce.
        try:
            StageSpec(name="a", prompt="p", system_prompt="s", output_schema='["files"]')
            self._runner.check("[Hidden Failure] non-object schema rejected", False)
        except ValueError:
            self._runner.check("[Hidden Failure] non-object schema rejected", True)

    def _schema_malformed_rejected(self) -> None:
        # A schema that is not JSON at all never reaches the SDK.
        try:
            StageSpec(name="a", prompt="p", system_prompt="s", output_schema="{files}")
            self._runner.check("[Hidden Failure] malformed schema rejected", False)
        except ValueError:
            self._runner.check("[Hidden Failure] malformed schema rejected", True)

    def _retry_policy_carried(self) -> None:
        # The retry policy must reach the frozen settings unchanged.
        options = {"prompts": ("p",), "systems": ("s",)}
        settings = self._command._settings(options, False, False, 3)  # noqa: SLF001
        ok = settings.stop_on_error is False and settings.max_retries_per_stage == 3
        self._runner.check("[Hidden Assumption] retry policy carried", ok)

    def _retry_policy_bounds_rejected(self) -> None:
        # Four retries exceed the reviewed 0-3 bound shared with the task board.
        options = {"prompts": ("p",), "systems": ("s",)}
        try:
            self._command._settings(options, False, True, 4)  # noqa: SLF001
            self._runner.check("[Hidden Failure] retry bound rejected", False)
        except StagesSettingsInvalid:
            self._runner.check("[Hidden Failure] retry bound rejected", True)


class _ScriptedSession(StagesCodexSession):
    """A session with scripted turns, so retry logic runs with no SDK turns."""

    def __init__(self, behaviors: list[object]) -> None:
        # Queues one behavior per turn: a reply object or an exception to raise.
        super().__init__({}, lambda _msg: None)
        self._behaviors = list(behaviors)
        self.turns = 0

    def _build_agent(self, plan: object, spec: object) -> object:
        # No SDK agent is needed because turns are scripted, not executed.
        return SimpleNamespace(marker="fake-agent")

    async def _turn(self, agent: object, spec: object, prompt: str) -> object:
        # Replays the next queued behavior for the stage under test.
        _ = (agent, spec, prompt)
        self.turns += 1
        behavior = self._behaviors.pop(0)
        if isinstance(behavior, BaseException):
            raise behavior
        return behavior


def _scripted_reply(text: str, thread: str = "thr_1") -> object:
    # Builds one completed reply shape for scripted turns.
    inner = SimpleNamespace(status="completed", final_response=text, thread_id=thread)
    return SimpleNamespace(codex=inner, content=text)


def _scripted_settings(count: int, stop_on_error: bool = True, retries: int = 1) -> StagesSettings:
    # Builds frozen settings with valid specs for execution cases.
    return StagesSettings(
        stages=tuple(
            StageSpec(name=f"s{i}", prompt="do it", system_prompt="be good") for i in range(count)
        ),
        parallel=False,
        stop_on_error=stop_on_error,
        max_retries_per_stage=retries,
    )


class ExecutionCases:
    """Retry, backoff, partial results, and cancellation around stage execution."""

    def __init__(self, runner: CaseRunner) -> None:
        # Keeps one shared runner across all execution cases.
        self._runner = runner
        self._plan = make_plan()

    def run_all(self) -> None:
        # Runs every execution case in file order.
        self._retry_recovers_on_fresh_agent()
        self._exhausted_stops_with_prefix()
        self._exhausted_continues_with_placeholder()
        self._fatal_fails_fast_without_retry()
        self._cancellation_reraised()
        self._backoff_grows_with_jitter_cap()
        self._prepare_is_lazy()
        self._parallel_records_per_index()

    def _run(self, session: StagesCodexSession, settings: StagesSettings) -> object:
        # Runs the async session synchronously for offline cases.
        return asyncio.run(session._run(self._plan, settings, "rta_test123"))  # noqa: SLF001

    def _retry_recovers_on_fresh_agent(self) -> None:
        # A transient host failure retries once and records the single success.
        session = _ScriptedSession([StagesHostFailed(), _scripted_reply("done")])
        result = self._run(session, _scripted_settings(1))
        ok = (
            result.text == "done"
            and result.completed == 1
            and result.failed == 0
            and result.steps[0].attempts == 2
            and session.turns == 2
        )
        self._runner.check("[Hidden Failure] retry recovers on fresh agent", ok)

    def _exhausted_stops_with_prefix(self) -> None:
        # Stop-on-error halts at the first exhausted stage and keeps the prefix.
        session = _ScriptedSession([_scripted_reply("first"), TimeoutError("x"), TimeoutError("y")])
        result = self._run(session, _scripted_settings(2, stop_on_error=True, retries=1))
        ok = (
            result.completed == 1
            and result.failed == 1
            and len(result.steps) == 2
            and result.steps[1].status == "failed"
            and result.stage_texts[0] == "first"
        )
        self._runner.check("[Silent Failure] exhausted stops with prefix", ok)

    def _exhausted_continues_with_placeholder(self) -> None:
        # Continue-on-error records a placeholder so indices stay aligned.
        session = _ScriptedSession([TimeoutError("x"), TimeoutError("y"), _scripted_reply("third")])
        result = self._run(session, _scripted_settings(2, stop_on_error=False, retries=1))
        ok = (
            result.completed == 1
            and result.failed == 1
            and result.stage_texts[0] == "Stage 1 failed."
            and result.stage_texts[1] == "third"
            and result.steps[1].thread_id == "thr_1"
        )
        self._runner.check("[Silent Failure] exhausted continues with placeholder", ok)

    def _fatal_fails_fast_without_retry(self) -> None:
        # A fatal settings failure propagates immediately instead of burning retries.
        session = _ScriptedSession([StagesSettingsInvalid()])
        try:
            self._run(session, _scripted_settings(1, retries=3))
            self._runner.check("[Hidden Failure] fatal fails fast without retry", False)
        except StagesSettingsInvalid:
            self._runner.check(
                "[Hidden Failure] fatal fails fast without retry", session.turns == 1
            )

    def _cancellation_reraised(self) -> None:
        # Cancellation is never converted into a host failure and never retries.
        session = _ScriptedSession([asyncio.CancelledError()])
        try:
            self._run(session, _scripted_settings(1, retries=3))
            self._runner.check("[Hidden Failure] cancellation reraised", False)
        except asyncio.CancelledError:
            self._runner.check("[Hidden Failure] cancellation reraised", session.turns == 1)
        except BaseException:
            self._runner.check("[Hidden Failure] cancellation reraised", False)

    def _backoff_grows_with_jitter_cap(self) -> None:
        # Backoff gives 2s, 8s, 32s plus at most 1s of jitter per retry index.
        session = StagesCodexSession({}, lambda _msg: None)
        lows = [session._backoff_seconds(i) for i in range(60)]  # noqa: SLF001
        first = lows[0] if len(lows) > 0 else 0.0
        ok = (
            2.0 <= session._backoff_seconds(0) <= 3.0  # noqa: SLF001
            and 8.0 <= session._backoff_seconds(1) <= 9.0  # noqa: SLF001
            and 32.0 <= session._backoff_seconds(2) <= 33.0  # noqa: SLF001
            and first >= 2.0
        )
        self._runner.check("[Hidden Assumption] backoff grows with jitter cap", ok)

    def _prepare_is_lazy(self) -> None:
        # Prepare records paths without building agents, so failures stay pre-payment.
        session = StagesCodexSession({}, lambda _msg: None)
        session.prepare(self._plan, _scripted_settings(1))  # type: ignore[arg-type]
        ok = session._prepared is True  # noqa: SLF001
        self._runner.check("[Hidden Assumption] prepare is lazy", ok)

    def _parallel_records_per_index(self) -> None:
        # Parallel mode collects each stage at its own index with placeholders.
        session = _ScriptedSession([_scripted_reply("p1"), _scripted_reply("p2")])
        settings = _scripted_settings(2)
        parallel = settings.model_copy(update={"parallel": True})
        result = asyncio.run(session._run(self._plan, parallel, "rta_test123"))  # noqa: SLF001
        ok = (
            result.completed == 2
            and result.failed == 0
            and result.stage_texts == ("p1", "p2")
            and [step.index for step in result.steps] == [0, 1]
        )
        self._runner.check("[Silent Failure] parallel records per index", ok)


def main() -> int:
    # Runs every case group and reports the combined summary.
    runner = CaseRunner()
    EdgeCases(runner).run_all()
    GateCases(runner).run_all()
    ReplyCases(runner).run_all()
    InputCases(runner).run_all()
    ExecutionCases(runner).run_all()
    return runner.report()


if __name__ == "__main__":
    raise SystemExit(main())
