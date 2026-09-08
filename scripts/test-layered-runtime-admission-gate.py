"""Offline adversarial contracts for paid runtime admission and Codex persistence."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from vidbyte.lib.dataclasses.codex import CodexRunResult, CodexUsage
from vidbyte.lib.enums.codex import CodexSandbox
from vidbyte.lib.errors import CodexAgentError

from vidbyte_cli.commands.runtime.persistence import PersistenceCommand
from vidbyte_cli.lib.constants.runtime import AdmissionReason
from vidbyte_cli.lib.constants.runtime import PersistenceProgress as Progress
from vidbyte_cli.lib.errors.failures import (
    PersistenceHostFailed,
    RuntimeAdmissionNotVerified,
    RuntimeExecutionNotImplemented,
)
from vidbyte_cli.lib.io import IOStreams
from vidbyte_cli.lib.runtime.context import ApplicationContext
from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor
from vidbyte_cli.lib.runtime_primitives.gate import RuntimeAdmissionGate
from vidbyte_cli.lib.runtime_primitives.hosts import RuntimeHostRegistry
from vidbyte_cli.lib.runtime_primitives.planner import RuntimeLaunchPlanner
from vidbyte_cli.lib.runtime_primitives.verification import RuntimeGrantVerifier
from vidbyte_cli.services.persistence.runner import PersistenceRunner
from vidbyte_cli.services.persistence.session import PersistentCodexSession
from vidbyte_cli.types.runtime import (
    PersistenceSettings,
    PersistenceStrength,
    RuntimeAdmissionCheck,
    RuntimeAdmissionGrant,
    RuntimeHost,
    RuntimeLaunchPlan,
)

KEY = "test-runtime-signing-key-never-a-production-secret"
SESSION = "11111111-1111-4111-8111-111111111111"


class AdmissionContracts(unittest.TestCase):
    """Protects signature binding, expiry and the final execution boundary."""

    def setUp(self) -> None:
        # Each test gets an independent current receipt and policy.
        self.now = datetime.now(UTC)
        self.gate = RuntimeAdmissionGate()
        self.plan = RuntimeLaunchPlan(
            capability_id="runtime.persistence@1",
            host=RuntimeHost.CODEX,
            executable=Path("codex"),
            working_directory=Path.cwd(),
            task="do thing",
        )
        self.grant = self._grant()

    def _grant(self, **changes: object) -> RuntimeAdmissionGrant:
        # Signs exactly the server wire fields with a test-only key.
        start = self.now - timedelta(seconds=1)
        end = start + timedelta(seconds=600)
        payload = {
            "admission_id": "rta_" + "a" * 32,
            "capability_id": "runtime.persistence",
            "version": "1",
            "user_id": "user",
            "api_key_id": "key",
            "charged_cents": 2,
            "idempotency_key_hash": hashlib.sha256(b"idem").hexdigest(),
            "admitted_at": start.isoformat(),
            "expires_at": end.isoformat(),
            **changes,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(KEY.encode(), canonical, hashlib.sha256).digest()
        token = ".".join(
            base64.urlsafe_b64encode(p).decode().rstrip("=") for p in (canonical, signature)
        )
        return RuntimeAdmissionGrant(
            admission_id="rta_" + "a" * 32,
            capability_id="runtime.persistence@1",
            execution_location="local",
            charged_cents=2,
            admitted_at=start,
            expires_at=end,
            grant_token=token,
        )

    def test_valid_signature_and_online_receipt(self) -> None:
        # Both trusted verification modes accept the exact intended receipt.
        self.assertTrue(self.gate.verify(self.plan, self.grant, self.now, KEY).admitted)
        self.assertTrue(self.gate.verify_online(self.plan, self.grant, self.grant).admitted)

    def test_checks_return_dataclasses_with_enum_reasons(self) -> None:
        check = self.gate._check_policy(self.plan, None, self.now)
        self.assertIsInstance(check, RuntimeAdmissionCheck)
        self.assertIs(check.reason, AdmissionReason.MISSING)
        self.assertFalse(check.passed)
        check = self.gate._check_time(self.grant, self.now)
        self.assertIsInstance(check, RuntimeAdmissionCheck)
        self.assertIs(check.reason, AdmissionReason.PASSED)
        self.assertTrue(check.passed)
        self.assertIsNone(self.gate.verify(self.plan, self.grant, self.now, KEY).reason)

    def test_missing_key_and_tampered_signature(self) -> None:
        # A missing secret must never turn off offline authentication.
        for key in (None, "", "incorrect"):
            self.assertFalse(self.gate.verify(self.plan, self.grant, self.now, key).admitted)
        bad = self.grant.model_copy(update={"grant_token": self.grant.grant_token + ".x"})
        self.assertFalse(self.gate.verify(self.plan, bad, self.now, KEY).admitted)

    def test_signed_claims_cannot_be_substituted(self) -> None:
        # A genuine token for another receipt cannot authorize this receipt's public fields.
        variants = (
            {"charged_cents": 25},
            {"capability_id": "runtime.same-host-ensemble"},
            {"admission_id": "rta_other"},
            {"version": "2"},
        )
        for fields in variants:
            with self.subTest(fields=fields):
                self.assertFalse(
                    self.gate.verify(self.plan, self._grant(**fields), self.now, KEY).admitted
                )

    def test_policy_rejects_unbounded_future_and_expired_receipts(self) -> None:
        # Rejects policy defects even when online verification returns the same object.
        variants = (
            {"expires_at": None},
            {"expires_at": self.now},
            {"expires_at": self.now + timedelta(days=1)},
            {"admitted_at": self.now + timedelta(seconds=1)},
            {"admitted_at": self.now.replace(tzinfo=None)},
            {"capability_id": "runtime.persistence"},
            {"charged_cents": 1},
            {"grant_token": None},
            {"admission_id": " "},
        )
        for fields in variants:
            bad = self.grant.model_copy(update=fields)
            with self.subTest(fields=fields):
                self.assertFalse(self.gate.verify_online(self.plan, bad, bad).admitted)
        self.assertFalse(self.gate.verify(self.plan, None, self.now, KEY).admitted)

    def test_online_must_return_identical_receipt(self) -> None:
        # Signature validation cannot authorize a different response envelope.
        other = self.grant.model_copy(update={"admission_id": "rta_other"})
        self.assertFalse(self.gate.verify_online(self.plan, self.grant, other).admitted)

    def test_decoder_rejects_malformed_and_oversized_tokens(self) -> None:
        # The strict decoder rejects oversized inputs and ignored whitespace.
        verifier = RuntimeGrantVerifier()
        for token in ("a.b.c", "x" * 9000, "!" * 10 + ".AAA", "AAA .AAA"):
            with self.subTest(token=token[:20]), self.assertRaises(ValueError):
                verifier.verify(token, KEY, self.now)
        data = self.grant.model_dump()
        data["extra"] = True
        with self.assertRaises(ValidationError):
            RuntimeAdmissionGrant.model_validate(data)

    def test_executor_denial_prevents_all_turns(self) -> None:
        # A negative or mismatched verdict must leave the session untouched.
        executor, session = RuntimeExecutor(), MagicMock(spec=PersistentCodexSession)
        settings = PersistenceSettings(strength=PersistenceStrength.TIER_1)
        verdict = self.gate.verify(self.plan, None, self.now, KEY)
        with self.assertRaises(RuntimeAdmissionNotVerified):
            PersistenceRunner(executor).run(self.plan, settings, session, verdict)
        session.run.assert_not_called()
        with self.assertRaises(RuntimeAdmissionNotVerified):
            executor.execute_adversarial_team(self.plan)
        valid = self.gate.verify(self.plan, self.grant, self.now, KEY)
        with self.assertRaises(RuntimeExecutionNotImplemented):
            executor.execute_adversarial_team(self.plan, valid)


class RecordingTransport:
    """Fakes native execution; the real SDK translates input and resumes its thread."""

    def __init__(self):
        self.calls = []
        self.results = []

    async def run(self, request):
        self.calls.append(request)
        if self.results:
            value = self.results.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        return CodexRunResult(
            thread_id=SESSION,
            turn_id="turn",
            status="completed",
            final_response="done",
            duration_ms=1,
            usage=CodexUsage(),
            items=(),
        )


class PersistenceContracts(unittest.TestCase):
    """Protects SDK continuity, exact input, progress and failure short-circuiting."""

    def setUp(self):
        self.original = "  Original {task}\nline\r\nUnicode: café. $(not-a-shell-command)  "
        self.plan = RuntimeLaunchPlanner(RuntimeHostRegistry(lambda _: "codex")).build(
            self.original, RuntimeHost.CODEX, Path.cwd(), "runtime.persistence@1"
        )
        self.progress = []
        self.session = PersistentCodexSession({"OPENAI_API_KEY": "fake"}, self.progress.append)
        self.transport = RecordingTransport()
        self.settings = PersistenceSettings(strength=PersistenceStrength.TIER_1)

    def _run(self, settings=None):
        with patch("vidbyte.agents.codex.agent.CodexTransport", return_value=self.transport):
            self.session.prepare(self.plan)
            return self.session.run(self.plan, settings or self.settings)

    def test_all_strengths_keep_exact_task_and_session(self):
        self.assertEqual(self.plan.task, self.original)
        for tier, expected in enumerate((6, 8, 20, 40, 70, 100), 1):
            self.transport.calls.clear()
            self.progress.clear()
            result = self._run(PersistenceSettings(strength=PersistenceStrength(tier)))
            calls = self.transport.calls
            self.assertEqual(len(calls), expected + 1)
            self.assertEqual(calls[0].thread_id, "")
            self.assertEqual(calls[0].prompt.items[0].text, self.original)
            self.assertEqual(result.continuation_turns, expected)
            self.assertEqual(result.session_id, SESSION)
            self.assertEqual(result.text, "done")
            for request in calls[1:]:
                self.assertEqual(request.thread_id, SESSION)
                prompt = request.prompt.items[0].text
                self.assertTrue(prompt.startswith("Very good job, keep working"))
                self.assertIn(
                    "Here is the original task in case your forgot " + self.original, prompt
                )
            self.assertEqual(self.progress[-2:], [Progress.FINAL, Progress.COMPLETE])
            self.assertTrue(all(not any(c.isdigit() for c in p) for p in self.progress))

    def test_provider_configuration_and_working_directory_reach_sdk(self):
        self._run()
        settings = self.transport.calls[0].settings
        self.assertEqual(settings.client.cwd, str(self.plan.working_directory))
        self.assertEqual(settings.client.codex_bin, str(self.plan.executable))
        self.assertEqual(settings.client.env["OPENAI_API_KEY"], "fake")
        self.assertEqual(settings.thread.sandbox, CodexSandbox.WORKSPACE_WRITE)
        self.assertIn('model_provider="vidbyte_openai"', settings.client.config_overrides)
        self.assertFalse(settings.thread.ephemeral)

    def test_incomplete_or_changed_thread_stops_continuation(self):
        good = CodexRunResult(
            thread_id=SESSION,
            turn_id="turn",
            status="completed",
            final_response="done",
            duration_ms=1,
            usage=CodexUsage(),
            items=(),
        )
        for changes in (
            {"thread_id": ""},
            {"thread_id": "different-thread"},
            {"status": "interrupted"},
            {"status": "failed"},
            {"final_response": None},
            {"final_response": ""},
        ):
            with self.subTest(changes=changes):
                self.transport.calls.clear()
                self.progress.clear()
                self.transport.results = [good, replace(good, **changes)]
                with self.assertRaises(PersistenceHostFailed):
                    self._run()
                self.assertEqual(len(self.transport.calls), 2)
                self.assertNotIn(Progress.COMPLETE, self.progress)

    def test_sdk_failure_is_safe_and_stops_all_later_turns(self):
        self.transport.results = [
            CodexAgentError(
                "secret task and credential", failure_code="CODEX_TURN_FAILED", operation="turn_run"
            )
        ]
        with self.assertRaises(PersistenceHostFailed) as caught:
            self._run()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertNotIn("secret task", str(caught.exception))
        self.assertNotIn(Progress.COMPLETE, self.progress)

    def test_timeout_cancels_active_sdk_turn(self):
        cancelled = []

        async def blocked(request):
            self.transport.calls.append(request)
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

        self.transport.run = blocked
        limits = SimpleNamespace(TURN_TIMEOUT_SECONDS=0.01)
        with patch("vidbyte_cli.services.persistence.session.PersistenceLimit", limits):
            with self.assertRaises(PersistenceHostFailed):
                self._run()
        self.assertEqual(cancelled, [True])
        self.assertEqual(len(self.transport.calls), 1)

    def test_cancellation_remains_cancellation(self):
        self.transport.results = [asyncio.CancelledError()]
        with self.assertRaises(asyncio.CancelledError):
            self._run()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertNotIn(Progress.COMPLETE, self.progress)

    def test_progress_covers_each_phase_without_loop_indices(self):
        self._run(PersistenceSettings(strength=PersistenceStrength.TIER_3))
        for phase in (Progress.EARLY, Progress.MIDDLE, Progress.LATE, Progress.FINAL):
            self.assertIn(phase, self.progress)
        self.assertEqual(self.progress[0], Progress.STARTING)
        self.assertEqual(self.progress[1], Progress.INITIAL_COMPLETE)


class PersistenceCommandContracts(AdmissionContracts):
    """Exercises command, gate, SDK facade and output with external boundaries faked."""

    def setUp(self):
        super().setUp()
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        self.context = ApplicationContext(
            IOStreams(io.StringIO(), self.stdout, self.stderr),
            environment={"OPENAI_API_KEY": "fake", "VIDBYTE_API_KEY": "private"},
        )
        self.endpoints = MagicMock()
        self.endpoints.admit_persistence.return_value = self.grant
        self.endpoints.verify_grant.return_value = self.grant
        self.transport = RecordingTransport()

    def _invoke(self):
        with (
            patch.object(
                self.context,
                "runtime_launch_planner",
                return_value=RuntimeLaunchPlanner(RuntimeHostRegistry(lambda _: "codex")),
            ),
            patch.object(self.context, "runtime_endpoints", return_value=self.endpoints),
            patch.object(self.context, "require_provider_credentials") as credentials,
            patch("vidbyte.agents.codex.agent.CodexTransport", return_value=self.transport),
        ):
            credentials.return_value.secret_value.return_value = "fake"
            PersistenceCommand().execute(self.context, self.plan.task, 1, "recover-admission")

    def test_one_admission_and_final_stdout_only(self):
        self._invoke()
        self.endpoints.admit_persistence.assert_called_once()
        self.endpoints.verify_grant.assert_called_once()
        self.assertEqual(len(self.transport.calls), 7)
        self.assertEqual(self.stdout.getvalue().strip(), "done")
        progress = self.stderr.getvalue()
        for message in (
            Progress.PREPARING,
            Progress.CREDENTIALS,
            Progress.ADMISSION,
            Progress.VERIFYING,
            Progress.ADMITTED,
            Progress.COMPLETE,
        ):
            self.assertIn(message, progress)
        self.assertNotIn("private", progress)
        self.assertEqual(self.transport.calls[0].settings.client.env["VIDBYTE_API_KEY"], "")
        request, key = self.endpoints.admit_persistence.call_args.args
        self.assertEqual(
            request.model_dump(), {"client_runtime_version": "1", "host": RuntimeHost.CODEX}
        )
        self.assertEqual(key, "recover-admission")

    def test_bad_receipt_never_starts_agent(self):
        self.endpoints.verify_grant.return_value = self.grant.model_copy(
            update={"admission_id": "rta_other"}
        )
        with self.assertRaises(RuntimeAdmissionNotVerified):
            self._invoke()
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertNotIn(Progress.ADMITTED, self.stderr.getvalue())

    def test_sdk_preparation_failure_precedes_payment(self):
        with patch(
            "vidbyte.agents.codex.CodexHarnessAgent",
            side_effect=CodexAgentError(
                "invalid",
                failure_code="CODEX_VIDBYTE_TRANSLATION_FAILED",
                operation="translate_agent",
            ),
        ):
            with self.assertRaises(CodexAgentError):
                self._invoke()
        self.endpoints.admit_persistence.assert_not_called()


if __name__ == "__main__":
    unittest.main()
