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

from vidbyte_cli.commands.agents.suggestion.request_builder import (  # noqa: E402
    SuggestionRequestBuilder,
)
from vidbyte_cli.services.suggestions.categories import SuggestionCategories  # noqa: E402
from vidbyte_cli.services.suggestions.context import SuggestionContextBuilder  # noqa: E402
from vidbyte_cli.services.suggestions.handoff import SuggestionHandoffBuilder  # noqa: E402
from vidbyte_cli.services.suggestions.prompts.library import SuggestionPrompts  # noqa: E402
from vidbyte_cli.services.suggestions.sdk import (  # noqa: E402
    SuggestionAgentSettingsInput,
    SuggestionSdk,
    SuggestionTextInput,
)
from vidbyte_cli.services.suggestions.selection import SuggestionSelection  # noqa: E402
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    SUGGESTIONS_HANDOFF_KIND,
    SUGGESTIONS_RESULT_KIND,
    SuggestionContextItem,
    SuggestionContextPrimitive,
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
        goal=goal,
        context=_context(goal),
        settings=SuggestionSettings(requested_count=count),
    )


def _context(
    goal: str, items: tuple[SuggestionContextItem, ...] = ()
) -> SuggestionContextPrimitive:
    return SuggestionContextPrimitive(
        goal=goal,
        description=(
            "This context defines the state used to create suggestions. It keeps records typed. "
            "It preserves omissions explicitly. It remains caller-supplied task data."
        ),
        items=items,
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
                context=_context("Probe"),
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
        built = SuggestionRequestBuilder().build(
            {
                "goal": "Build through the dedicated request collaborator",
                "count": 1,
                "categories": ("verification", "experiment"),
                "mistakes": ("bad merge | stale base | use current main",),
            }
        )
        results.check(
            "[Review Comment] request builder owns parsing behind one interface",
            built.settings.categories == ("verification", "experiment")
            and built.context_items[0].kind == "mistake",
        )
        rendered = built.context.to_context_text()
        results.check(
            "[Review Comment] custom primitive explains the context and each item",
            "complete context from which the suggestion agent" in built.context.description
            and built.context_items[0].description.count(".") in (1, 2)
            and "## [ctx-001] mistake (mistake)" in rendered,
        )
        from vidbyte.context import ContextManager

        managed = ContextManager((built.context,)).to_context()
        results.check(
            "[Review Comment] Vidbyte SDK ContextManager accepts the custom primitive",
            len(managed.context_items) == 1
            and managed.context_items[0].kind == "suggestion-context",
        )
        sdk = SuggestionSdk.load()
        generator = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role="generator",
                system_prompt="Generator system prompt",
                context=built.context,
                provider="openai",
                model="gpt-test",
            )
        )
        critic = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role="critic", system_prompt="Critic system prompt", context=built.context
            )
        )
        generator_manager = generator.context_manager
        critic_manager = critic.context_manager
        results.check(
            "[Review Comment] generator and critic receive separate SDK context managers",
            generator_manager is not critic_manager
            and generator_manager.get_by_id("suggestion-context:request") is built.context
            and critic_manager.get_by_id("suggestion-context:request") is built.context,
        )
        results.check(
            "[Review Comment] provider and model survive the strict SDK input boundary",
            generator.codex.thread.model_provider == "openai"
            and generator.codex.thread.model == "gpt-test",
        )
        try:
            SuggestionAgentSettingsInput(role="generator", system_prompt="", context=built.context)
            results.check("[Review Comment] SDK dataclass inputs reject invalid values", False)
        except ValueError:
            results.check("[Review Comment] SDK dataclass inputs reject invalid values", True)
        sdk.run_input(SuggestionTextInput("Review candidates."))
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
        expanded = builder.build(
            {
                "mistake": ("bad merge | stale base | target current main",),
                "forbidden": ("force push main",),
                "approach": (
                    "worked: preserve additive registrations",
                    "untried: isolate the package check",
                    "failed: rewrite unrelated commands",
                    "rejected: force a model call during help",
                ),
                "outcome": ("The earlier fix shipped but increased latency.",),
                "blocker": ("Release waits on CI.",),
                "hypothesis": ("low: the editable SDK is current",),
                "risk": ("The editable SDK may point at another worktree.",),
                "trajectory": ("User asked for review; parent inspected the PR.",),
            },
            {},
        )
        results.check(
            "[Review Comment] expanded context types retain distinct manifest kinds",
            {item.kind for item in expanded.items}
            == {
                "mistake",
                "forbidden",
                "approach",
                "outcome",
                "blocker",
                "hypothesis",
                "risk",
                "trajectory",
            },
        )
        expanded_context = _context("Choose the next safe release step", expanded.items)
        contextual = self.service.run(
            SuggestionRequest(
                goal="Choose the next safe release step",
                context=expanded_context,
                settings=SuggestionSettings(requested_count=1),
            )
        )
        from vidbyte.context import ContextManager

        expanded_manager = ContextManager((expanded_context,))
        managed_context = expanded_manager.to_context()
        results.check(
            "[Review Comment] full parent trajectory reaches the SDK context window",
            managed_context.context_items[0] is expanded_context
            and "User asked for review; parent inspected the PR."
            in expanded_context.to_context_text(),
        )
        packet = contextual.ideas[0].handoff
        results.check(
            "[Review Comment] final handoff preserves warnings and exact prohibitions",
            "bad merge | stale base | target current main" in packet.warnings
            and packet.forbidden_actions == ("force push main",)
            and bool(packet.suggested_actions)
            and bool(packet.decisions_along_way)
            and bool(packet.considerations),
        )
        results.check(
            "[Review Comment] cited evidence is embedded instead of leaving a bare ref",
            bool(packet.evidence)
            and packet.evidence[0].ref == contextual.ideas[0].evidence_refs[0]
            and packet.evidence[0].content == "bad merge | stale base | target current main",
        )
        generated = contextual.ideas[0]
        action_text = " ".join(generated.suggested_actions).lower()
        results.check(
            "[Review Comment] approach, outcome, hypothesis, and risk context change actions",
            "worked" in action_text
            and "untried approach" in action_text
            and "observed outcome" in action_text
            and "confirm or refute" in action_text
            and "mitigation" in action_text
            and "low-confidence hypothesis" in generated.review_summary.lower()
            and "rewrite unrelated commands" not in action_text
            and "force a model call during help" not in action_text,
        )
        results.check(
            "[Review Comment] hypothesis context prioritizes an investigative category",
            generated.primary_category in ("experiment", "investigation"),
        )
        prohibited = builder.build({"forbidden": ("force push main",)}, {})
        blocked_result = self.service.run(
            SuggestionRequest(
                goal="force push main",
                context=_context("force push main", prohibited.items),
                settings=SuggestionSettings(requested_count=1),
            )
        )
        results.check(
            "[Review Comment] candidates requiring a forbidden action are cut",
            blocked_result.ideas == (),
        )
        blocker_context = builder.build({"blocker": ("Release waits on CI.",)}, {})
        blocker_result = self.service.run(
            SuggestionRequest(
                goal="Choose a release step",
                context=_context("Choose a release step", blocker_context.items),
                settings=SuggestionSettings(requested_count=3),
            )
        )
        results.check(
            "[Review Comment] blockers produce unblocking ideas and defer dependent ideas",
            any(
                "clear or route around" in idea.first_action.lower()
                for idea in blocker_result.ideas
            )
            and any(
                idea.horizon.value == "later" and idea.readiness.value == "blocked"
                for idea in blocker_result.ideas
            ),
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
        request = _request(count=2)
        outcome = self.service.run(request)
        idea = outcome.ideas[0]
        rebuilt = builder.build(idea, request)
        results.check(
            "[Silent Failure] every idea carries required handoff slots",
            len(rebuilt.suggested_actions) > 0
            and len(rebuilt.completion_checks) > 0
            and len(rebuilt.stop_conditions) > 0,
        )
        results.check(
            "[Hidden Assumption] authority defaults to not-granted",
            rebuilt.authority == "not_granted_by_this_handoff",
        )
        first = builder.render_prompt(rebuilt)
        altered = rebuilt.model_copy(update={"suggested_actions": ("Something else entirely",)})
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
            "[Review Comment] every category has the complete detailed definition",
            all(
                item.description
                and item.goal
                and item.intent
                and item.timeline
                and len(item.checklist) >= 3
                and item.cautions
                for item in registry.definitions()
            ),
        )
        selected = registry.prompt_section(("verification", "experiment"))
        results.check(
            "[Review Comment] selected category prompts include every requested definition",
            "# Verification" in selected
            and "# Experiment" in selected
            and "# Continuation" not in selected,
        )
        results.check(
            "[Hidden Failure] categories drive validation",
            registry.is_known("verification") and not registry.is_known("nope"),
        )

    def check_cli_contracts(self) -> None:
        # Process-level contracts: envelope, streams, credential-free reads.
        results = self.results
        help_result = _run_cli(["agents", "suggest", "run", "--help"])
        results.check(
            "[Review Comment] every expanded context input is visible to callers",
            help_result.returncode == 0
            and all(
                name in help_result.stdout
                for name in (
                    "--mistakes",
                    "--forbidden",
                    "--approaches",
                    "--outcomes",
                    "--blockers",
                    "--hypotheses",
                    "--risks",
                    "--trajectory",
                )
            ),
        )
        categories = _run_cli(["--json", "agents", "suggest", "categories"])
        try:
            document = json.loads(categories.stdout)
            kind_ok = document.get("kind") == "suggestions.categories"
            visible_categories = document.get("data", {}).get("categories", [])
        except json.JSONDecodeError:
            kind_ok, visible_categories = False, []
        results.check(
            "[Hidden Assumption] categories works without credentials",
            categories.returncode == 0 and kind_ok,
        )
        results.check(
            "[Review Comment] agents can view every detailed category",
            len(visible_categories) == 17
            and all(
                all(field in item for field in ("description", "goal", "intent", "timeline"))
                for item in visible_categories
            ),
        )
        multiple = _run_cli(
            [
                "--json",
                "agents",
                "suggest",
                "run",
                "--goal",
                "Choose two complementary checks",
                "--count",
                "4",
                "--category",
                "verification",
                "--category",
                "experiment",
            ]
        )
        try:
            multiple_document = json.loads(multiple.stdout)
            multiple_ideas = multiple_document.get("data", {}).get("ideas", [])
            selected_categories = {item.get("primary_category") for item in multiple_ideas}
        except json.JSONDecodeError:
            selected_categories = set()
        results.check(
            "[Review Comment] agents can select and use multiple categories",
            multiple.returncode == 0 and selected_categories == {"verification", "experiment"},
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
