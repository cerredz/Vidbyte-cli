"""Offline contract checks for actionable API-balance exhaustion errors."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from click import Group
from click.testing import CliRunner
from x402.http.utils import encode_payment_required_header
from x402.schemas import PaymentRequired

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.billing import BillingTopUpCommand  # noqa: E402
from vidbyte_cli.lib.api.client import ApiClient  # noqa: E402
from vidbyte_cli.lib.api.endpoints.billing import BillingEndpoints  # noqa: E402
from vidbyte_cli.lib.api.problem import ApiProblemMapper  # noqa: E402
from vidbyte_cli.lib.api.runtime_payment import RuntimePayment  # noqa: E402
from vidbyte_cli.lib.auth.credentials import Credentials  # noqa: E402
from vidbyte_cli.lib.config.models import ResolvedConfig  # noqa: E402
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    ApiCreditExhausted,
    BillingTopUpApprovalRequired,
)
from vidbyte_cli.lib.output.models import OutputDocument  # noqa: E402

_TOP_UP_URL = "https://api.example.test/agent/topup"
_TOP_UP_SECRET = "0x" + "11" * 32
_TOP_UP_ENV = {"VIDBYTE_X402_PRIVATE_KEY": _TOP_UP_SECRET}
_TOP_UP_REQUIREMENT = {
    "x402Version": 2,
    "resource": {
        "url": _TOP_UP_URL,
        "description": "Vidbyte API balance top-up",
        "mimeType": "application/json",
    },
    "accepts": [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "amount": "5000000",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "payTo": "0x2222222222222222222222222222222222222222",
            "maxTimeoutSeconds": 60,
            "extra": {"name": "USD Coin", "version": "2"},
        }
    ],
}


def _body(code: str = "api_usage_exhausted") -> dict[str, object]:
    return {
        "error": True,
        "title": "Vidbyte API balance exhausted",
        "subtitle": "Add Vidbyte API balance before starting this agent.",
        "description": "Detailed recovery instructions.",
        "code": code,
        "incident_id": "abc123def456",
        "remediation": {
            "action": "top_up_api_balance",
            "requires_user_approval": True,
            "topup_method": "POST",
            "topup_path": "/agent/topup",
            "cli_command": "vidbyte-cli billing top-up --confirm",
            "minimum_topup_cents": 500,
            "supported_payment_methods": ["x402", "mpp"],
            "browser_url": "https://vidbyte.pro/settings/api",
            "retry_original_operation": True,
            "steps": ["Get approval", "Top up", "Verify", "Retry"],
        },
    }


def _response(body: object) -> httpx.Response:
    return httpx.Response(
        402,
        json=body,
        headers={"content-type": "application/json", "x-request-id": "request-1"},
        request=httpx.Request(
            "POST", "https://api.example.test/api/x402/runtime/persistence/activate"
        ),
    )


def _run(name: str, check) -> tuple[str, bool, str]:
    try:
        check()
    except Exception as error:  # noqa: BLE001 - the script reports each contract failure.
        return name, False, f"{type(error).__name__}: {error}"
    return name, True, ""


def main() -> int:
    cases = [
        (
            "[Edge Case] valid exhaustion maps to exit 5",
            lambda: _assert_valid_mapping(),
        ),
        (
            "[Hidden Failure] malformed body uses safe fallback",
            lambda: _assert_fallback_mapping(),
        ),
        (
            "[Silent Failure] remediation survives machine output",
            lambda: _assert_machine_output(),
        ),
        (
            "[Hidden Assumption] unrelated 402 is not specialized",
            lambda: _assert_unrelated_mapping(),
        ),
        (
            "[Edge Case] mid-run exhaustion keeps recovery metadata",
            lambda: _assert_mid_run_mapping(),
        ),
        (
            "[Edge Case] top-up help is side-effect free",
            lambda: _assert_help(),
        ),
        (
            "[Hidden Failure] top-up requires explicit approval",
            lambda: _assert_approval(),
        ),
        (
            "[Edge Case] explicit top-up pays one exact challenge",
            lambda: _assert_top_up_payment(),
        ),
    ]
    results = [_run(name, check) for name, check in cases]
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'} {name}{': ' + detail if detail else ''}")
    passed = sum(item[1] for item in results)
    print(f"{passed}/{len(results)} tests passed")
    return 0 if passed == len(results) else 1


def _assert_valid_mapping() -> None:
    error = ApiProblemMapper().from_response(_response(_body()))
    assert isinstance(error, ApiCreditExhausted)
    assert error.exit_code == 5
    assert error.remediation is not None
    assert error.remediation["topup_path"] == "/agent/topup"
    assert "get explicit approval" in error.description.lower()


def _assert_fallback_mapping() -> None:
    error = ApiProblemMapper().from_response(_response({"error": True, "code": "other"}))
    assert isinstance(error, ApiCreditExhausted)
    assert error.remediation is None
    assert "Vidbyte account" in error.message


def _assert_machine_output() -> None:
    error = ApiProblemMapper().from_response(_response(_body()))
    encoded = OutputDocument.from_error(error).model_dump_json()
    assert "remediation" in encoded
    assert "requires_user_approval" in encoded
    assert "private_key" not in encoded


def _assert_unrelated_mapping() -> None:
    error = ApiProblemMapper().from_response(_response({"error": True, "code": "payment_required"}))
    assert isinstance(error, ApiCreditExhausted)
    assert error.remediation is None


def _assert_mid_run_mapping() -> None:
    error = ApiProblemMapper().from_response(_response(_body("usage_credit_exhausted")))
    assert isinstance(error, ApiCreditExhausted)
    assert error.remediation is not None
    assert error.remediation["cli_command"] == "vidbyte-cli billing top-up --confirm"


def _assert_help() -> None:
    group = Group()
    BillingTopUpCommand().register(group)
    result = CliRunner().invoke(group, ["top-up", "--help"])
    assert result.exit_code == 0, result.output
    assert "--confirm" in result.output


def _assert_approval() -> None:
    try:
        BillingTopUpCommand().execute(None, False, None)  # type: ignore[arg-type]
    except BillingTopUpApprovalRequired:
        return
    raise AssertionError("missing confirmation did not fail")


def _assert_top_up_payment() -> None:
    requests: list[httpx.Request] = []

    def response() -> httpx.Response:
        required = PaymentRequired.model_validate(_TOP_UP_REQUIREMENT)
        header = encode_payment_required_header(required)
        return httpx.Response(
            402,
            headers={"PAYMENT-REQUIRED": header},
            request=httpx.Request("POST", _TOP_UP_URL),
        )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return response()
        return httpx.Response(
            200,
            json={
                "credited_cents": 500,
                "rail": "x402",
                "payment_ref": "pay-1",
                "available_balance_cents": 500,
            },
            headers={"content-type": "application/json"},
            request=request,
        )

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
    try:
        result = BillingEndpoints(client).top_up(
            "top-up-idempotency", RuntimePayment(_TOP_UP_ENV, 500)
        )
    finally:
        client.close()
    assert result.credited_cents == 500
    assert len(requests) == 2
    assert all(request.headers["Idempotency-Key"] == "top-up-idempotency" for request in requests)
    assert "PAYMENT-SIGNATURE" not in requests[0].headers
    assert "PAYMENT-SIGNATURE" in requests[1].headers
    assert _TOP_UP_SECRET not in requests[1].headers["PAYMENT-SIGNATURE"]


if __name__ == "__main__":
    raise SystemExit(main())
