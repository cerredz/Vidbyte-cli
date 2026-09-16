"""Verifies the expanded suggestion context and version-2 handoff contract.

Run with `python scripts/test-suggestion-handoff-context.py`. The cases are
offline and instantiate the service, typed models, and handoff builder directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))

from vidbyte_cli.services.suggestions.handoff import SuggestionHandoffBuilder  # noqa: E402
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    SuggestionContextItem,
    SuggestionHandoff,
    SuggestionProblem,
    SuggestionRequest,
    SuggestionSettings,
)


class Results:
    """Collects labeled outcomes and chooses the process exit status."""

    def __init__(self) -> None:
        # Counts are kept separately so each failure remains visible.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        # Prints each result immediately so a failed case is easy to locate.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
            return
        self.failed += 1
        suffix = f" - {detail}" if detail else ""
        print(f"FAIL: {name}{suffix}", file=sys.stderr)

    def summary(self) -> int:
        # Returns nonzero whenever any labeled case failed.
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


class SuggestionHandoffContextSuite:
    """Runs contract, rendering, extraction, and packaging checks."""

    def __init__(self, results: Results) -> None:
        # The deterministic service is the only generator used by this suite.
        self.results = results
        self.service = SuggestionService()
        self.builder = SuggestionHandoffBuilder()

    def run(self) -> None:
        # Keeps the cases grouped by the contract boundary they exercise.
        self.check_complete_context()
        self.check_validation()
        self.check_rendering()
        self.check_extraction()
        self.check_cli_and_assets()

    def check_complete_context(self) -> None:
        # Confirms a goal-only idea still carries explicit bounded reasoning.
        result = self.service.run(
            SuggestionRequest(
                goal="Improve handoff quality",
                context_items=(),
                settings=SuggestionSettings(requested_count=1),
            )
        )
        idea = result.ideas[0]
        handoff = idea.handoff
        context = handoff.suggestion_context
        self.results.check(
            "[Edge Case] goal-only context is complete",
            bool(context.core_insight)
            and bool(context.verification_plan)
            and bool(context.tradeoffs)
            and bool(context.risks)
            and bool(context.unknowns),
        )
        self.results.check(
            "[Silent Failure] existing idea metadata is preserved",
            handoff.suggestion_title == idea.title
            and handoff.suggestion_summary == idea.summary
            and handoff.primary_category == idea.primary_category
            and handoff.horizon == idea.horizon
            and handoff.relationship == idea.relationship
            and handoff.readiness == idea.readiness
            and handoff.expected_benefit == idea.expected_benefit
            and handoff.effort_estimate == idea.effort_estimate
            and handoff.review_summary == idea.review_summary,
        )
        self.results.check(
            "[Silent Failure] proposed action is distinct from first action",
            handoff.selected_action == idea.proposed_action
            and handoff.selected_action != idea.first_action,
        )
        self.results.check(
            "[Hidden Assumption] no caller evidence is not fabricated",
            handoff.evidence_refs == () and "no caller evidence" in context.confidence.basis[0],
        )
        maximum_goal = "g" * 4096
        maximum = (
            self.service.run(
                SuggestionRequest(
                    goal=maximum_goal,
                    context_items=(),
                    settings=SuggestionSettings(requested_count=1),
                )
            )
            .ideas[0]
            .handoff
        )
        self.results.check(
            "[Edge Case] maximum goal remains lossless and bounded",
            len(maximum.original_goal) == 4096 and len(maximum.execution_prompt) <= 16384,
        )

    def check_validation(self) -> None:
        # Exercises strict nested validation and field bounds.
        result = self.service.run(
            SuggestionRequest(
                goal="Validate a handoff",
                context_items=(),
                settings=SuggestionSettings(requested_count=1),
            )
        )
        payload = result.ideas[0].handoff.model_dump(mode="json")
        payload["handoff_version"] = 1
        try:
            SuggestionHandoff.model_validate(payload)
        except Exception:
            self.results.check("[Hidden Failure] version 1 handoff is rejected", True)
        else:
            self.results.check("[Hidden Failure] version 1 handoff is rejected", False)
        try:
            SuggestionProblem(
                type="problem",
                condition="x" * 2049,
                consequence="A consequence",
                affected_area="area",
            )
        except Exception:
            self.results.check("[Edge Case] overlong nested value is rejected", True)
        else:
            self.results.check("[Edge Case] overlong nested value is rejected", False)

    def check_rendering(self) -> None:
        # Checks every major context section and deterministic field mutation.
        result = self.service.run(
            SuggestionRequest(
                goal="Render useful context",
                context_items=(),
                settings=SuggestionSettings(requested_count=1),
            )
        )
        handoff = result.ideas[0].handoff
        rendered = handoff.execution_prompt
        expected_fragments = (
            handoff.suggestion_title,
            handoff.suggestion_context.core_insight,
            handoff.suggestion_context.causal_rationale,
            handoff.suggestion_context.scope.in_scope[0],
            handoff.suggestion_context.decision_points[0].response,
            "Verification plan:",
            handoff.suggestion_context.verification_plan[0].procedure,
            handoff.suggestion_context.risks[0].guard,
            handoff.suggestion_context.unknowns[0].question,
            handoff.suggestion_context.cost_of_inaction,
            handoff.suggestion_context.reversibility.recovery,
            handoff.suggestion_context.alternatives_considered[0].alternative,
            f"Authority: {handoff.authority}",
        )
        self.results.check(
            "[Silent Failure] prompt renders all major context sections",
            all(fragment in rendered for fragment in expected_fragments),
        )
        altered_context = handoff.suggestion_context.model_copy(
            update={"core_insight": "A changed insight for the renderer."}
        )
        altered = handoff.model_copy(update={"suggestion_context": altered_context})
        self.results.check(
            "[Silent Failure] context mutation changes prompt",
            "A changed insight for the renderer." in self.builder.render_prompt(altered),
        )
        self.results.check(
            "[Hidden Assumption] authority cannot be granted by context",
            handoff.authority == "not_granted_by_this_handoff",
        )
        with_caller_context = (
            self.service.run(
                SuggestionRequest(
                    goal="Render caller constraints",
                    context_items=(
                        SuggestionContextItem(
                            ref="ctx-001",
                            kind="constraint",
                            label="Caller constraint",
                            content="No network changes",
                            source="test",
                        ),
                    ),
                    settings=SuggestionSettings(requested_count=1),
                )
            )
            .ideas[0]
            .handoff
        )
        self.results.check(
            "[Silent Failure] caller constraints reach execution prompt",
            "No network changes" in with_caller_context.execution_prompt
            and "Constraints:" in with_caller_context.execution_prompt,
        )

    def check_extraction(self) -> None:
        # Uses the public extraction command to verify the versioned packet path.
        result = self.service.run(
            SuggestionRequest(
                goal="Extract a handoff",
                context_items=(),
                settings=SuggestionSettings(requested_count=1),
            )
        )
        path = _REPOSITORY_ROOT / "test-suggestion-handoff-context-result.json"
        try:
            document = {
                "schema_version": 1,
                "kind": "suggestions.result",
                "data": result.model_dump(mode="json"),
            }
            path.write_text(json.dumps(document), encoding="utf-8")
            completed = self._run_cli(
                [
                    "--json",
                    "agents",
                    "suggest",
                    "handoff",
                    "--input",
                    str(path),
                    "--idea",
                    result.ideas[0].id,
                ]
            )
            try:
                extracted = json.loads(completed.stdout)
            except json.JSONDecodeError:
                extracted = {}
            self.results.check(
                "[Hidden Failure] extraction emits version 2 without a model",
                completed.returncode == 0 and extracted.get("data", {}).get("handoff_version") == 2,
            )
        finally:
            path.unlink(missing_ok=True)

    def check_cli_and_assets(self) -> None:
        # Confirms help remains credential-free and source assets are present.
        help_result = self._run_cli(["agents", "suggest", "handoff", "--help"])
        self.results.check(
            "[Hidden Assumption] handoff help needs no provider",
            help_result.returncode == 0,
        )
        assets = (
            _REPOSITORY_ROOT / "src/vidbyte_cli/services/suggestions/prompts/generator.md",
            _REPOSITORY_ROOT / "src/vidbyte_cli/services/suggestions/prompts/critic.md",
        )
        self.results.check(
            "[Edge Case] changed prompt assets exist",
            all(path.is_file() and path.stat().st_size > 0 for path in assets),
        )

    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        # Runs the public module against this worktree's source package.
        import os

        environment = dict(os.environ)
        source = str(_REPOSITORY_ROOT / "src")
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
        return subprocess.run(
            [sys.executable, "-m", "vidbyte_cli", *args],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )


def main() -> int:
    # Runs every focused case and returns the aggregate status.
    results = Results()
    SuggestionHandoffContextSuite(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
