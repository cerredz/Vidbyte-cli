"""Offline contracts for explicit x402 payment and the shared database-verified gate.

Uses real signing/schema code with a fake HTTP transport. No financial transaction,
provider model call, credential storage or public-network request is made.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from click import Group
from click.testing import CliRunner
from x402.http.utils import encode_payment_required_header
from x402.schemas import PaymentRequired

from vidbyte_cli.commands.runtime.persistence import PersistenceCommand
from vidbyte_cli.lib.api.client import ApiClient
from vidbyte_cli.lib.api.runtime_payment import RuntimePayment
from vidbyte_cli.lib.auth.credentials import Credentials
from vidbyte_cli.lib.config.models import ResolvedConfig
from vidbyte_cli.lib.constants.runtime import RuntimePaymentConfig as Config
from vidbyte_cli.lib.errors.cli_error import CliError
from vidbyte_cli.lib.errors.failures import RuntimePaymentFailed
from vidbyte_cli.types.runtime import RuntimeX402AdmissionRequest

URL = "https://api.example.test/api/x402/runtime/persistence/activate"
PATH = "/api/x402/runtime/persistence/activate"
SECRET = "0x" + "11" * 32
ENV = {Config.PRIVATE_KEY_ENV: SECRET}
REQUIREMENT = {
    "x402Version": 2,
    "resource": {"url": URL, "description": "Runtime admission", "mimeType": "application/json"},
    "accepts": [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "amount": "20000",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "payTo": "0x2222222222222222222222222222222222222222",
            "maxTimeoutSeconds": 60,
            "extra": {"name": "USD Coin", "version": "2"},
        }
    ],
}


class PaymentTests(unittest.TestCase):
    """Validate actual SDK authorization and the client's HTTP boundary."""

    def response(self, data=None):
        # Encode a real standard v2 header rather than mocking the SDK parser.
        required = PaymentRequired.model_validate(data or REQUIREMENT)
        header = encode_payment_required_header(required)
        return httpx.Response(
            402, headers={"PAYMENT-REQUIRED": header}, request=httpx.Request("POST", URL)
        )

    def test_real_signing_once(self):
        """[Silent Failure] A valid exact challenge produces one standard authorization."""
        payer = RuntimePayment(ENV, 2)
        headers = payer.headers(self.response())
        self.assertIn("PAYMENT-SIGNATURE", headers)
        self.assertNotIn(SECRET, json.dumps(headers))
        with self.assertRaises(RuntimePaymentFailed):
            payer.headers(self.response())

    def test_invalid_requirements(self):
        """[Hidden Assumption] Incorrect payment requirements cannot be signed."""
        mutations = (
            ("network", "eip155:84532"),
            ("amount", "20001"),
            ("amount", "0"),
            ("asset", "0x3333333333333333333333333333333333333333"),
            ("scheme", "upto"),
            ("extra", {"name": "Wrong", "version": "2"}),
            ("payTo", "0x0000000000000000000000000000000000000000"),
            ("maxTimeoutSeconds", 3601),
            ("maxTimeoutSeconds", 0),
        )
        for field, value in mutations:
            required = copy.deepcopy(REQUIREMENT)
            required["accepts"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(RuntimePaymentFailed):
                RuntimePayment(ENV, 2).headers(self.response(required))

    def test_resource_and_options(self):
        """[Silent Failure] A different origin/resource or ambiguous payment options are refused."""
        for url in (
            "https://other.test" + PATH,
            URL + "/other",
            URL + "?extra=yes",
            "//other.test" + PATH,
        ):
            required = copy.deepcopy(REQUIREMENT)
            required["resource"]["url"] = url
            with self.subTest(url=url), self.assertRaises(RuntimePaymentFailed):
                RuntimePayment(ENV, 2).headers(self.response(required))
        required = copy.deepcopy(REQUIREMENT)
        required["accepts"] *= 2
        with self.assertRaises(RuntimePaymentFailed):
            RuntimePayment(ENV, 2).headers(self.response(required))

    def test_missing_malformed_or_oversized_challenge(self):
        """[Edge Case] Missing, malformed, or oversized headers never cause signing."""
        for value in ("", "bad", "a" * (Config.MAX_CHALLENGE_CHARACTERS + 1)):
            response = httpx.Response(
                402, headers={"PAYMENT-REQUIRED": value}, request=httpx.Request("POST", URL)
            )
            with self.subTest(length=len(value)), self.assertRaises(RuntimePaymentFailed):
                RuntimePayment(ENV, 2).headers(response)

    def test_bad_credentials_and_network(self):
        """[Hidden Assumption] Explicit payment requires a valid signer and reviewed network."""
        for env in (
            {},
            {Config.PRIVATE_KEY_ENV: "invalid"},
            ENV | {Config.NETWORK_ENV: "eip155:1"},
        ):
            with (
                self.subTest(env_keys=list(env)),
                self.assertRaises(RuntimePaymentFailed) as caught,
            ):
                RuntimePayment(env, 2)
            self.assertNotIn(SECRET, str(caught.exception))

    def client(self, handler):
        # Exercise the actual API client with its origin, credential and retry policies intact.
        client = ApiClient(
            ResolvedConfig(
                profile="default",
                api_url="https://api.example.test",
                output_format="human",
                color="never",
                request_timeout_seconds=30,
                provenance={},
            ),
            Credentials.from_value("vb_live_test"),
        )
        client._transport = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return client

    def test_probe_sign_retry_identically(self):
        """[Hidden Failure] Transient paid retry reuses signature, body and idempotency identity."""
        requests = []

        def handler(request):
            # First probe challenges, first paid attempt fails transiently, then succeeds.
            requests.append(request)
            if len(requests) == 1:
                return self.response()
            return httpx.Response(503 if len(requests) == 2 else 200, json={"ok": True})

        client = self.client(handler)
        payer = RuntimePayment(ENV, 2)
        with patch("vidbyte_cli.lib.api.client.time.sleep"):
            response = client.post_runtime_payment(
                PATH, RuntimeX402AdmissionRequest(host="codex"), "runtime-test-key", payer
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(requests), 3)
        self.assertNotIn("PAYMENT-SIGNATURE", requests[0].headers)
        self.assertEqual(
            requests[1].headers["PAYMENT-SIGNATURE"], requests[2].headers["PAYMENT-SIGNATURE"]
        )
        self.assertEqual(len({request.content for request in requests}), 1)
        self.assertEqual({r.headers["Idempotency-Key"] for r in requests}, {"runtime-test-key"})
        self.assertEqual({r.headers["x-api-key"] for r in requests}, {"vb_live_test"})

    def test_repeated_402_is_not_reauthorized(self):
        """[Hidden Failure] A second 402 fails without a new authorization or wallet fallback."""
        calls = []

        def handler(request):
            # Both unpaid and paid attempts return a challenge to test the no-resign rule.
            calls.append(request)
            return self.response()

        client = self.client(handler)
        with self.assertRaises(RuntimePaymentFailed):
            client.post_runtime_payment(
                PATH,
                RuntimeX402AdmissionRequest(host="codex"),
                "runtime-test-key",
                RuntimePayment(ENV, 2),
            )
        self.assertEqual(len(calls), 2)

    def test_replay_does_not_sign(self):
        """[Silent Failure] Receipt recovery does not create a payment authorization."""
        client = self.client(lambda _: httpx.Response(200, json={"recovered": True}))
        payer = RuntimePayment(ENV, 2)
        with patch.object(payer, "headers") as signer:
            response = client.post_runtime_payment(
                PATH, RuntimeX402AdmissionRequest(host="codex"), "runtime-test-key", payer
            )
        self.assertEqual(response.status_code, 200)
        signer.assert_not_called()

    def test_auth_errors_do_not_pay(self):
        """[Hidden Assumption] Authentication and permission rejection cannot initiate payment."""
        for status in (401, 403, 409):
            client = self.client(lambda _, status=status: httpx.Response(status, json={}))
            payer = RuntimePayment(ENV, 2)
            with patch.object(payer, "headers") as signer, self.assertRaises(CliError):
                client.post_runtime_payment(
                    PATH, RuntimeX402AdmissionRequest(host="codex"), "runtime-test-key", payer
                )
            signer.assert_not_called()

    def test_help_option(self):
        """[Edge Case] Help advertises payment opt-in without loading credentials."""
        group = Group()
        PersistenceCommand().register(group)
        result = CliRunner().invoke(group, ["persistence", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--with-x402-payment", result.output)


class Results(unittest.TextTestResult):
    """Emit labeled contract outcomes and preserve failure traces."""

    def addSuccess(self, test):
        # Print the behavioral promise on success.
        super().addSuccess(test)
        self.stream.writeln("PASS " + (test.shortDescription() or str(test)))

    def addFailure(self, test, err):
        # Include explicit failure labels and normal unittest diagnostics.
        super().addFailure(test, err)
        self.stream.writeln("FAIL " + str(test))

    def addError(self, test, err):
        # Unexpected runtime errors are failures rather than skipped coverage.
        super().addError(test, err)
        self.stream.writeln("FAIL " + str(test))


class CommandTests(unittest.TestCase):
    """Verify payment opt-in reaches the existing SDK launch gate with no secret inheritance."""

    def setUp(self):
        # Reuse the established command/SDK fixture rather than imitate its launch behavior.
        source = Path(__file__).with_name("test-layered-runtime-admission-gate.py")
        spec = importlib.util.spec_from_file_location("payment_command_fixture", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.case = module.PersistenceCommandContracts()
        self.case.setUp()
        self.case.context.environment = dict(self.case.context.environment) | ENV
        self.case.endpoints.admit_persistence_x402.return_value = self.case.grant
        self.addCleanup(self.case.context.close)

    def invoke(self):
        # Drive the actual explicit command branch while retaining real SDK fake-transport checks.
        execute = PersistenceCommand.execute

        def paid(ctx, task, strength, key):
            # Enable the public option without changing the existing fixture's assertions.
            return execute(PersistenceCommand(), ctx, task, strength, key, True)

        with patch.object(PersistenceCommand, "execute", side_effect=paid):
            self.case._invoke()

    def test_x402_verifies_before_sdk_and_filters_secret(self):
        """[Silent Failure] Opt-in verifies online and clears payment secrets from Codex."""
        self.invoke()
        endpoints = self.case.endpoints
        endpoints.admit_persistence.assert_not_called()
        endpoints.admit_persistence_x402.assert_called_once()
        endpoints.verify_grant.assert_called_once()
        request = endpoints.admit_persistence_x402.call_args.args[0]
        self.assertTrue(request.with_x402_payment)
        self.assertEqual(len(self.case.transport.calls), 7)
        env = self.case.transport.calls[0].settings.client.env
        self.assertEqual(env[Config.PRIVATE_KEY_ENV], "")
        self.assertNotIn(SECRET, self.case.stdout.getvalue() + self.case.stderr.getvalue())

    def test_failed_database_verification_never_launches(self):
        """[Hidden Failure] Database verification outage never launches a turn."""
        self.case.endpoints.verify_grant.side_effect = RuntimePaymentFailed("database_unavailable")
        with self.assertRaises(RuntimePaymentFailed):
            self.invoke()
        self.assertEqual(self.case.transport.calls, [])
        self.assertEqual(self.case.stdout.getvalue(), "")


class Runner:
    """Include the existing full command/gate/SDK contracts in this feature's verification."""

    def run(self):
        # Existing default-flow tests prove that adding x402 preserves wallet behavior.
        source = Path(__file__).with_name("test-layered-runtime-admission-gate.py")
        spec = importlib.util.spec_from_file_location("existing_runtime_contracts", source)
        existing = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(existing)
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(existing))
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, resultclass=Results, verbosity=0).run(suite)
        print(stream.getvalue())
        passed = result.testsRun - len(result.failures) - len(result.errors)
        print(f"{passed}/{result.testsRun} tests passed")
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(Runner().run())
