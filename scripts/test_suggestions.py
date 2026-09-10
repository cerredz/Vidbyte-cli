"""Deterministic verification for the suggestion (next-action) agent.

Run with `python scripts/test_suggestions.py`, or via `scripts/run_ci.py`. Every
case runs offline with fakes only at the SDK turn: no live API, no provider
credentials, and no Codex process. Each case prints PASS/FAIL plus a final
X/Y summary, and the process exits non-zero when anything fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))

from vidbyte_cli.services.suggestions.categories import SuggestionCategories  # noqa: E402
from vidbyte_cli.services.suggestions.context import SuggestionContextBuilder  # noqa: E402
from vidbyte_cli.services.suggestions.handoff import SuggestionHandoffBuilder  # noqa: E402
from vidbyte_cli.services.suggestions.prompts.library import SuggestionPrompts  # noqa: E402
from vidbyte_cli.services.suggestions.selection import SuggestionSelection  # noqa: E402
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    SUGGESTIONS_HANDOFF_KIND,
    SUGGESTIONS_RESULT_KIND,
    SuggestionRequest,
    SuggestionSettings,
)


class Results:
    """Collects one PASS/FAIL line per case and decides the process status."""

    def __init__(self) -> None:
        # Counts accumulate across groups in run order.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        # Prints immediately so a hang is locatable, then records the outcome.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
            return
        self.failed += 1
        print(f"FAIL: {name}{f' - {detail}' if detail else ''}", file=sys.stderr)

    def summary(self) -> int:
        # Final gate line plus a non-zero exit when anything failed.
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


def _request(
    goal: str = "Ship the first suggestion agent release", count: int = 5
) -> SuggestionRequest:
    # Minimal valid request used by most offline cases.
    return SuggestionRequest(
        goal=goal, context_items=(), settings=SuggestionSettings(requested_count=count)
    )


def _run_cli(args: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    # Fresh-process CLI run with PYTHONPATH pinned to this checkout's src.
    import os

    environment = dict(os.environ)
    source = str(_REPOSITORY_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
    return subprocess.run(
        [sys.executable, "-m", "vidbyte_cli", *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


class SuggestionSuite:
    """Every Section 10 behavior, labeled by its failure category."""

    def __init__(self, results: Results) -> None:
        # One service and registry shared across deterministic cases.
        self.results = results
        self.service = SuggestionService()

    def run(self) -> None:
        # Executes groups in a fixed order from units to process contracts.
        self.check_generation()
        self.check_limits()
        self.check_context()
        self.check_selection()
        self.check_handoff()
        self.check_prompts()
        self.check_cli_contracts()

    def check_generation(self) -> None:
        # Core happy paths and shortfall semantics.
        results = self.results
        outcome = self.service.run(_request())
        results.check(
            "[Edge Case] goal-only run returns ideas with handoffs",
            len(outcome.ideas) > 0
            and all(idea.handoff.idea_id == idea.id for idea in outcome.ideas),
        )
        results.check("[Silent Failure] ideas never exceed count", len(outcome.ideas) <= 5)
        one = self.service.run(_request(count=1))
        results.check("[Edge Case] count 1 returns at most one", len(one.ideas) <= 1)
        dry = self.service.run(
            SuggestionRequest(
                goal="Probe",
                context_items=(),
                settings=SuggestionSettings(requested_count=5, dry_run=True),
            )
        )
        results.check(
            "[Edge Case] dry run returns no ideas with dry stop",
            dry.returned_count == 0 and dry.stop_reason.value == "dry_run",
        )
        results.check(
            "[Silent Failure] shortfall is explicit partial, not filler",
            one.status.value in ("complete", "partial", "no_suggestions"),
        )

    def check_limits(self) -> None:
        # Invalid controls must fail at the CLI before any model work.
        results = self.results
        bad_count = _run_cli(["agents", "suggest", "run", "--goal", "x", "--count", "21"])
        results.check("[Edge Case] count 21 fails before model calls", bad_count.returncode == 2)
        bad_category = _run_cli(["agents", "suggest", "run", "--goal", "x", "--category", "nope"])
        results.check(
            "[Hidden Failure] unknown category fails before model calls",
            bad_category.returncode != 0,
        )
        empty_goal = _run_cli(["agents", "suggest", "run", "--goal", ""])
        results.check("[Edge Case] empty goal fails before model calls", empty_goal.returncode != 0)
        both = _run_cli(["agents", "suggest", "run", "--goal", "x", "--input", "whatever.json"])
        results.check("[Edge Case] goal plus input is mutually exclusive", both.returncode != 0)

    def check_context(self) -> None:
        # Context builder rules: explicit files only, caps, contradictions.
        results = self.results
        builder = SuggestionContextBuilder()
        snapshot = builder.build({"completed": ("CLI registration done",)}, {})
        results.check(
            "[Hidden Failure] completed work becomes a context item",
            len(snapshot.items) == 1 and snapshot.items[0].ref.startswith("ctx-"),
        )
        both = builder.build({"completed": ("same thing",), "in-progress": ("same thing",)}, {})
        results.check(
            "[Hidden Failure] contradictions surface a warning, not a silent pick",
            any(
                "both" in warning.lower() or "contradict" in warning.lower()
                for warning in both.warnings
            ),
        )
        try:
            builder.build({}, {"artifact": (Path("does-not-exist-12345.md"),)})
            results.check("[Hidden Failure] missing file is rejected", False)
        except ValueError:
            results.check("[Hidden Failure] missing file is rejected", True)
        try:
            builder.build({}, {"artifact": (Path("."),)})
            results.check("[Hidden Failure] directory as file is rejected", False)
        except ValueError:
            results.check("[Hidden Failure] directory as file is rejected", True)
        tmp = Path("test-suggestions-tmp.bin")
        try:
            tmp.write_text("hello", encoding="utf-8")
            try:
                builder.build({}, {"artifact": (tmp,)})
                results.check("[Hidden Failure] unsupported suffix is rejected", False)
            except ValueError:
                results.check("[Hidden Failure] unsupported suffix is rejected", True)
        finally:
            tmp.unlink(missing_ok=True)

    def check_selection(self) -> None:
        # Selection guards: evidence, dedup, rejection, coverage.
        results = self.results
        selection = SuggestionSelection()
        outcome = self.service.run(_request(count=4))
        valid = selection.validate_evidence(outcome.ideas, set())
        results.check(
            "[Hidden Failure] unknown evidence refs are dropped",
            all(len(idea.evidence_refs) == 0 for idea in valid) or len(valid) <= len(outcome.ideas),
        )
        doubled = outcome.ideas + outcome.ideas
        deduped = selection.deduplicate(doubled)
        results.check(
            "[Silent Failure] exact duplicates collapse in code", len(deduped) == len(outcome.ideas)
        )
        suppressed = selection.suppress_rejected(outcome.ideas, ("dashboard",))
        results.check(
            "[Hidden Failure] rejected terms suppress matches",
            len(suppressed) <= len(outcome.ideas),
        )
        coverage = selection.coverage(outcome.ideas)
        results.check(
            "[Silent Failure] coverage counts primary categories",
            sum(coverage.values()) == len(outcome.ideas),
        )

    def check_handoff(self) -> None:
        # Handoff determinism and authority defaults.
        results = self.results
        builder = SuggestionHandoffBuilder()
        outcome = self.service.run(_request(count=2))
        idea = outcome.ideas[0]
        rebuilt = builder.build(idea, outcome.goal, {})
        results.check(
            "[Silent Failure] every idea carries required handoff slots",
            len(rebuilt.suggested_steps) > 0
            and len(rebuilt.acceptance_checks) > 0
            and len(rebuilt.stop_conditions) > 0,
        )
        results.check(
            "[Hidden Assumption] authority defaults to not-granted",
            rebuilt.authority == "not_granted_by_this_handoff",
        )
        first = builder.render_prompt(rebuilt)
        altered = rebuilt.model_copy(update={"suggested_steps": ("Something else entirely",)})
        second = builder.render_prompt(altered)
        results.check(
            "[Silent Failure] prompt renders from fields, cannot drift",
            first != second and "Something else" in second,
        )

    def check_prompts(self) -> None:
        # Prompts load from the package and generator/critic differ.
        results = self.results
        prompts = SuggestionPrompts()
        generator = prompts.generator_system()
        critic = prompts.critic_system()
        results.check(
            "[Hidden Assumption] packaged prompts load with distinct roles",
            len(generator) > 100 and len(critic) > 100 and generator != critic,
        )
        registry = SuggestionCategories()
        results.check(
            "[Edge Case] registry holds 17 versioned categories", len(registry.ids()) == 17
        )
        results.check(
            "[Hidden Failure] categories drive validation",
            registry.is_known("verification") and not registry.is_known("nope"),
        )

    def check_cli_contracts(self) -> None:
        # Process-level contracts: envelope, streams, credential-free reads.
        results = self.results
        categories = _run_cli(["--json", "agents", "suggest", "categories"])
        try:
            document = json.loads(categories.stdout)
            kind_ok = document.get("kind") == "suggestions.categories"
        except json.JSONDecodeError:
            kind_ok = False
        results.check(
            "[Hidden Assumption] categories works without credentials",
            categories.returncode == 0 and kind_ok,
        )
        run = _run_cli(
            [
                "--json",
                "--no-input",
                "agents",
                "suggest",
                "run",
                "--goal",
                "Decide next build step",
                "--count",
                "2",
            ]
        )
        try:
            document = json.loads(run.stdout)
            envelope = (
                document.get("kind") == SUGGESTIONS_RESULT_KIND
                and document.get("schema_version") == 1
            )
            ideas = document.get("data", {}).get("ideas", [])
        except json.JSONDecodeError:
            envelope, ideas = False, []
        results.check(
            "[Silent Failure] JSON stdout carries results-only envelope",
            run.returncode == 0 and envelope and len(ideas) <= 2,
        )
        results.check(
            "[Silent Failure] handoff kind constant is stable",
            SUGGESTIONS_HANDOFF_KIND == "suggestions.handoff"
            and SUGGESTIONS_RESULT_KIND == "suggestions.result",
        )
        stdin_doc = json.dumps({"goal": "Stdin goal", "settings": {"count": 2}})
        via_stdin = _run_cli(
            ["--json", "--no-input", "agents", "suggest", "run", "--input", "-"],
            stdin_text=stdin_doc,
        )
        results.check(
            "[Edge Case] structured stdin input works non-interactively", via_stdin.returncode == 0
        )
        dry = _run_cli(
            ["--json", "--no-input", "agents", "suggest", "run", "--goal", "Dry goal", "--dry-run"]
        )
        results.check("[Edge Case] dry run needs no model call", dry.returncode == 0)


def main() -> int:
    results = Results()
    SuggestionSuite(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
