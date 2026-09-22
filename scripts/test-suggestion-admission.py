"""Verification script for the suggestion agent's priced admission.

Offline only: no network, no Codex turns, no credentials. The endpoints, the planner, the SDK
loader, and the service are fakes at their typed boundaries, while Click parsing, the request
builder, the admission gate, and the renderer are the real ones. Each case prints PASS/FAIL and
the script exits non-zero when any case fails.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import click
from click.testing import CliRunner

from vidbyte_cli.commands.agents.suggestion import suggest as suggest_module
from vidbyte_cli.commands.agents.suggestion.suggest import SuggestRunCommand
from vidbyte_cli.lib.errors.failures import SuggestionSdkUnavailable
from vidbyte_cli.lib.runtime_primitives.gate import RuntimeAdmissionGate
from vidbyte_cli.services.suggestions.service import SuggestionService
from vidbyte_cli.types.runtime import (
    RuntimeAdmissionGrant,
    RuntimeAdmissionRequest,
    RuntimeHost,
    RuntimeLaunchPlan,
    RuntimeSuggestionAdmissionRequest,
)
from vidbyte_cli.types.suggestions import SuggestionResult


class CaseRunner:
    """Collects labeled results and renders the final summary."""

    def __init__(self) -> None:
        # Starts with no recorded outcomes.
        self.results: list[tuple[str, bool]] = []

    def check(self, name: str, ok: bool) -> None:
        # Records and prints one case immediately so a crash still shows progress.
        self.results.append((name, ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}")

    def report(self) -> int:
        # Returns the process status for the whole script.
        passed = sum(1 for _, ok in self.results if ok)
        print(f"{passed}/{len(self.results)} suggestion admission cases passed")
        return 0 if passed == len(self.results) else 1


def make_grant(capability_id: str, cents: int) -> RuntimeAdmissionGrant:
    # Builds a grant with a live time window for policy checks.
    now = datetime.now(UTC)
    return RuntimeAdmissionGrant(
        admission_id="rta_suggest01",
        capability_id=capability_id,
        execution_location="local",
        charged_cents=cents,
        admitted_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(seconds=600),
        grant_token="x" * 32,
    )


def make_plan(capability_id: str) -> RuntimeLaunchPlan:
    # Builds a launch plan without host discovery.
    return RuntimeLaunchPlan(
        capability_id=capability_id,  # type: ignore[arg-type]
        host=RuntimeHost.CODEX,
        executable=Path("."),
        working_directory=Path("."),
        task="Ship the billing page",
    )


class FakeEndpoints:
    """Records admission and verification calls, and prices a grant at two cents per unit."""

    def __init__(self, events: list[str], cents_per_unit: int = 2) -> None:
        self.events = events
        self.requests: list[tuple[RuntimeSuggestionAdmissionRequest, str]] = []
        self._cents = cents_per_unit
        self._grant: RuntimeAdmissionGrant | None = None

    def admit_suggestion(
        self, request: RuntimeSuggestionAdmissionRequest, key: str
    ) -> RuntimeAdmissionGrant:
        self.events.append("admit")
        self.requests.append((request, key))
        self._grant = make_grant("runtime.suggestion@1", self._cents * request.units)
        return self._grant

    def verify_grant(self, request: object) -> RuntimeAdmissionGrant:
        self.events.append("verify")
        assert self._grant is not None
        return self._grant


class FakePlanner:
    """Returns a plan for the requested capability and records that host discovery ran."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def build(self, task: str, host: object, cwd: Path, capability_id: str) -> RuntimeLaunchPlan:
        self.events.append("plan")
        return make_plan(capability_id)


class FakeOutput:
    """Captures diagnostics and the one result document the command emits."""

    def __init__(self) -> None:
        self.diagnostics: list[str] = []
        self.documents: list[dict[str, Any]] = []
        self.human: list[str] = []

    def diagnostic(self, message: str) -> None:
        self.diagnostics.append(str(message))

    def result(self, document: Any, human: str) -> None:
        self.documents.append(document.data)
        self.human.append(human)


class FakeContext:
    """The slice of ApplicationContext the suggest-run command reaches."""

    def __init__(self, events: list[str], cents_per_unit: int = 2) -> None:
        self.events = events
        self._output = FakeOutput()
        self.endpoints = FakeEndpoints(events, cents_per_unit)
        self._planner = FakePlanner(events)

    def output(self) -> FakeOutput:
        return self._output

    def paths(self) -> None:
        return None

    def runtime_launch_planner(self) -> FakePlanner:
        return self._planner

    def runtime_endpoints(self) -> FakeEndpoints:
        self.events.append("endpoints")
        return self.endpoints


class FakeService:
    """Records the SDK it was built with and returns a real, empty completed result."""

    built_with: list[object] = []

    def __init__(self, sdk: object | None = None) -> None:
        FakeService.built_with.append(sdk)

    def run(self, request: Any) -> SuggestionResult:
        # The real service renders the envelope; dry_run keeps it from touching an SDK.
        settings = request.settings.model_copy(update={"dry_run": True})
        return SuggestionService().run(request.model_copy(update={"settings": settings}))


def invoke(context: FakeContext, loader: Any, *args: str) -> Any:
    # Runs the real Click command with the fake context as its object.
    group = click.Group(name="suggest")
    SuggestRunCommand(sdk_loader=loader).register(group)
    return CliRunner().invoke(group, ["run", *args], obj=context, catch_exceptions=True)


def loader_for(events: list[str], sdk: object) -> Any:
    # Returns an SDK loader that records when it ran.
    def load() -> object:
        events.append("sdk")
        return sdk

    return load


class Cases:
    """Every case runs against fresh fakes."""

    def __init__(self, runner: CaseRunner) -> None:
        self.r = runner

    def run_all(self) -> None:
        suggest_module.SuggestionService = FakeService  # type: ignore[misc,assignment]
        self._wire_shape()
        self._units_per_count()
        self._gate_prices_per_unit()
        self._dry_run_never_admits()
        self._paid_run_order_and_receipt()
        self._sdk_failure_never_admits()
        self._bad_key_never_admits()
        self._explicit_key_is_sent()
        self._price_drift_is_refused()
        self._old_results_still_load()

    def _wire_shape(self) -> None:
        # Only suggestion admissions carry units; every other runtime keeps two fields.
        request = RuntimeSuggestionAdmissionRequest(host=RuntimeHost.CODEX, units=2)
        dumped = request.model_dump(mode="json")
        plain = RuntimeAdmissionRequest(host=RuntimeHost.CODEX).model_dump(mode="json")
        try:
            RuntimeSuggestionAdmissionRequest(host=RuntimeHost.CODEX, units=3)
            too_many = False
        except ValueError:
            too_many = True
        self.r.check(
            "suggestion admission sends units and nothing else new",
            dumped == {"client_runtime_version": "1", "host": "codex", "units": 2}
            and plain == {"client_runtime_version": "1", "host": "codex"}
            and too_many,
        )

    def _units_per_count(self) -> None:
        # 2-10 requested ideas buy one unit and 11-15 buy two.
        seen = {}
        for count in ("2", "10", "11", "15"):
            events: list[str] = []
            context = FakeContext(events)
            invoke(context, loader_for(events, object()), "--goal", "Ship it", "--count", count)
            seen[count] = [request.units for request, _ in context.endpoints.requests]
        self.r.check(
            "units are ceil(count / 10)",
            seen == {"2": [1], "10": [1], "11": [2], "15": [2]},
        )

    def _gate_prices_per_unit(self) -> None:
        # The gate multiplies the per-unit price for suggestion and leaves stages at 1x.
        gate = RuntimeAdmissionGate()
        plan = make_plan("runtime.suggestion@1")
        two = make_grant("runtime.suggestion@1", 4)
        one = make_grant("runtime.suggestion@1", 2)
        stages = make_grant("runtime.stages@1", 1)
        self.r.check(
            "gate expects two cents per unit",
            gate.verify_online(plan, two, two, 2).admitted
            and gate.verify_online(plan, one, one, 1).admitted
            and not gate.verify_online(plan, two, two, 1).admitted
            and gate.verify_online(make_plan("runtime.stages@1"), stages, stages).admitted,
        )

    def _dry_run_never_admits(self) -> None:
        # A dry run loads no SDK, binds no endpoints, and reports no admission.
        events: list[str] = []
        context = FakeContext(events)
        result = invoke(context, loader_for(events, object()), "--goal", "Ship it", "--dry-run")
        document = context.output().documents[0] if context.output().documents else {}
        self.r.check(
            "dry run is never admitted or charged",
            result.exit_code == 0 and events == [] and document.get("admission") is None,
        )

    def _paid_run_order_and_receipt(self) -> None:
        # SDK and host are proven before the purchase, and the service reuses that SDK.
        events: list[str] = []
        sdk = object()
        context = FakeContext(events)
        FakeService.built_with = []
        result = invoke(context, loader_for(events, sdk), "--goal", "Ship it", "--count", "12")
        document = context.output().documents[0] if context.output().documents else {}
        self.r.check(
            "paid run checks SDK and host, then admits once and verifies",
            result.exit_code == 0 and events == ["sdk", "plan", "endpoints", "admit", "verify"],
        )
        self.r.check(
            "service runs with the SDK loaded before payment", FakeService.built_with == [sdk]
        )
        self.r.check(
            "result reports the charge, units, and admission id",
            document.get("admission")
            == {"admission_id": "rta_suggest01", "charged_cents": 4, "units": 2}
            and "Vidbyte charge: 4 cents" in context.output().human[0],
        )

    def _sdk_failure_never_admits(self) -> None:
        # A missing SDK fails while the run is still free.
        events: list[str] = []
        context = FakeContext(events)

        def broken() -> object:
            events.append("sdk")
            raise SuggestionSdkUnavailable(ImportError("vidbyte.agents.codex"))

        result = invoke(context, broken, "--goal", "Ship it")
        self.r.check(
            "SDK failure stops before any purchase",
            result.exit_code != 0 and "admit" not in events and "endpoints" not in events,
        )

    def _bad_key_never_admits(self) -> None:
        # A malformed key fails before the SDK import or any network binding.
        events: list[str] = []
        context = FakeContext(events)
        result = invoke(
            context,
            loader_for(events, object()),
            "--goal",
            "Ship it",
            "--idempotency-key",
            "bad key",
        )
        self.r.check("malformed key stops before any work", result.exit_code != 0 and events == [])

    def _explicit_key_is_sent(self) -> None:
        # A caller-chosen key reaches the admission unchanged so a retry recovers the purchase.
        events: list[str] = []
        context = FakeContext(events)
        invoke(
            context,
            loader_for(events, object()),
            "--goal",
            "Ship it",
            "--idempotency-key",
            "ci-job-4821",
        )
        keys = [key for _, key in context.endpoints.requests]
        self.r.check("explicit key is the admission key", keys == ["ci-job-4821"])

    def _price_drift_is_refused(self) -> None:
        # A backend receipt at the wrong price is refused before any model runs.
        events: list[str] = []
        context = FakeContext(events, cents_per_unit=3)
        FakeService.built_with = []
        result = invoke(context, loader_for(events, object()), "--goal", "Ship it")
        self.r.check(
            "mispriced receipt never reaches the service",
            result.exit_code != 0 and FakeService.built_with == [],
        )

    def _old_results_still_load(self) -> None:
        # Results saved before pricing have no admission field and must still validate for handoff.
        events: list[str] = []
        context = FakeContext(events)
        invoke(context, loader_for(events, object()), "--goal", "Ship it", "--dry-run")
        saved = dict(context.output().documents[0])
        saved.pop("admission", None)
        loaded = SuggestionResult.model_validate(json.loads(json.dumps(saved)))
        self.r.check("pre-pricing results still load", loaded.admission is None)


if __name__ == "__main__":
    runner = CaseRunner()
    Cases(runner).run_all()
    sys.exit(runner.report())
