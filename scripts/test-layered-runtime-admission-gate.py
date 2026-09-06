"""Offline adversarial contracts for paid runtime admission and Codex persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from vidbyte_cli.lib.errors.failures import (
    PersistenceHostFailed,
    RuntimeAdmissionNotVerified,
    RuntimeExecutionNotImplemented,
)
from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor
from vidbyte_cli.lib.runtime_primitives.gate import RuntimeAdmissionGate
from vidbyte_cli.lib.runtime_primitives.hosts import RuntimeHostRegistry
from vidbyte_cli.lib.runtime_primitives.persistence import PersistentCodexSession
from vidbyte_cli.lib.runtime_primitives.planner import RuntimeLaunchPlanner
from vidbyte_cli.lib.runtime_primitives.verification import RuntimeGrantVerifier
from vidbyte_cli.types.runtime import (
    PersistenceSettings,
    PersistenceStrength,
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
            executor.execute_persistence(self.plan, settings, session, verdict)
        session.run.assert_not_called()
        with self.assertRaises(RuntimeAdmissionNotVerified):
            executor.execute_adversarial_team(self.plan)
        valid = self.gate.verify(self.plan, self.grant, self.now, KEY)
        with self.assertRaises(RuntimeExecutionNotImplemented):
            executor.execute_adversarial_team(self.plan, valid)


class RecordingSession(PersistentCodexSession):
    """Uses real prompt assembly and event parsing with a deterministic host boundary."""

    def __init__(self) -> None:
        # Holds only the inputs needed to assert actual turn and resume behavior.
        super().__init__({"OPENAI_API_KEY": "fake"}, lambda _: None)
        self.calls = []

    def _execute(self, arguments, cwd, prompt, events) -> None:
        # Emits the documented protocol without contacting Codex or any provider.
        self.calls.append((arguments, cwd, prompt))
        for event in (
            {"type": "thread.started", "thread_id": SESSION},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
            {"type": "turn.completed"},
        ):
            events.write(json.dumps(event) + "\n")


class PersistenceContracts(unittest.TestCase):
    """Proves exact task preservation and bounded same-session continuation."""

    def test_process_stdin_is_exact_utf8_and_failure_stops(self) -> None:
        # Binary stdin avoids newline conversion on Windows and keeps task text off argv.
        session = PersistentCodexSession({"OPENAI_API_KEY": "fake"}, lambda _: None)
        process = MagicMock()
        process.returncode = 0
        factory = MagicMock()
        factory.return_value.__enter__.return_value = process
        original = "  exact\nline\r\nUnicode café  "
        with patch("vidbyte_cli.lib.runtime_primitives.persistence.subprocess.Popen", factory):
            session._execute(["codex", "exec", "-"], Path.cwd(), original, io.StringIO())
            self.assertEqual(process.communicate.call_args.args[0], original.encode("utf-8"))
            self.assertNotIn(original, factory.call_args.args[0])
            process.returncode = 1
            with self.assertRaises(PersistenceHostFailed):
                session._execute(["codex", "exec", "-"], Path.cwd(), original, io.StringIO())

    def test_all_strengths_keep_exact_task_and_session(self) -> None:
        # Covers boundary tiers and every intermediate mapping through the actual run loop.
        original = "  Original {task}\nUnicode: café. $(not-a-shell-command)  "
        planner = RuntimeLaunchPlanner(RuntimeHostRegistry(lambda _: "codex"))
        plan = planner.build(original, RuntimeHost.CODEX, Path.cwd(), "runtime.persistence@1")
        self.assertEqual(plan.task, original)
        for tier, expected in enumerate((6, 8, 20, 40, 70, 100), 1):
            session = RecordingSession()
            result = session.run(plan, PersistenceSettings(strength=PersistenceStrength(tier)))
            self.assertEqual(len(session.calls), expected + 1)
            self.assertEqual(session.calls[0][2], original)
            self.assertEqual(result.continuation_turns, expected)
            self.assertEqual(result.session_id, SESSION)
            for args, _, prompt in session.calls[1:]:
                self.assertIn("resume", args)
                self.assertIn(SESSION, args)
                self.assertNotIn(original, args)
                self.assertTrue(prompt.startswith("Very good job, keep working"))
                self.assertIn("Here is the original task in case your forgot " + original, prompt)

    def test_incomplete_or_changed_session_fails(self) -> None:
        # Nonzero exits are not the only failure signal: missing protocol state also fails.
        session = RecordingSession()
        streams = (
            "",
            "not json\n",
            "[]\n",
            '{"type":"turn.failed"}\n',
            '{"type":"thread.started","thread_id":"not-a-session"}\n',
            '{"type":"turn.completed"}\n',
        )
        for stream in streams:
            with self.subTest(stream=stream), self.assertRaises(PersistenceHostFailed):
                session._parse_events(io.StringIO(stream), None)
        with self.assertRaises(PersistenceHostFailed):
            session._session_id("22222222-2222-4222-8222-222222222222", SESSION)


if __name__ == "__main__":
    unittest.main()
