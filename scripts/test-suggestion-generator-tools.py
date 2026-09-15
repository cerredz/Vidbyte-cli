"""Offline verification for generator-owned suggestion store tools."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.services.suggestions.store import SuggestionStore  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    ContextManifestEntry,
    SuggestionContextItem,
    SuggestionContextPrimitive,
    SuggestionDraft,
    SuggestionRequest,
    SuggestionSettings,
)


class Results:
    """Prints one labelled result per contract and returns a process status."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool) -> None:
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
        else:
            self.failed += 1
            print(f"FAIL: {name}", file=sys.stderr)

    def finish(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return int(self.failed > 0)


def _request() -> SuggestionRequest:
    item = SuggestionContextItem(
        ref="ctx-001",
        kind="trajectory",
        label="trajectory",
        description="The caller supplied current state for the suggestion run.",
        content="The current state is available for one bounded check.",
        source="flag:trajectory",
    )
    manifest = ContextManifestEntry(
        ref=item.ref,
        kind=item.kind,
        source=item.source,
        chars=len(item.content),
        sha256=hashlib.sha256(item.content.encode()).hexdigest()[:16],
    )
    goal = "Make the next action explicit"
    return SuggestionRequest(
        goal=goal,
        context=SuggestionContextPrimitive(
            goal=goal,
            description="The context bounds this offline store test.",
            items=(item,),
        ),
        context_manifest=(manifest,),
        settings=SuggestionSettings(requested_count=2, categories=("verification", "experiment")),
    )


def _draft(
    title: str, *, category: str = "verification", idea_id: str | None = None
) -> SuggestionDraft:
    """Builds one valid draft for the store contract tests."""
    return SuggestionDraft(
        idea_id=idea_id,
        title=title,
        summary="Take one bounded action that produces useful evidence.",
        primary_category=category,
        why_now="The current state is available for a focused check.",
        expected_benefit="The next decision becomes easier to make.",
        evidence_refs=("ctx-001",),
        assumptions=("The caller can inspect the relevant state.",),
        dependencies=("The current task remains available.",),
        first_action="Inspect the current state and record the smallest useful check.",
        suggested_actions=("Inspect the current state.", "Record the result."),
        decision_points=("Continue only if the check changes the decision.",),
        considerations=tuple(f"Material consideration {i}." for i in range(1, 9)),
        completion_criteria="A dated result is recorded.",
        effort_estimate="Small bounded check",
    )


def main() -> int:
    """Runs edge, failure, silent-failure, and assumption checks for the store."""
    results = Results()
    request = _request()
    seed = SuggestionService(sdk=object())._ideas_from_drafts((_draft("Initial action"),), request)
    store = SuggestionStore(request, ("verification", "experiment"))
    store.seed(seed)

    # [Edge Case] A valid add receives a host-owned stable identity.
    results.check(
        "valid add returns stable ID",
        "Stored suggestion idea-002"
        in store.add_suggestion("experiment", _draft("Second action", category="experiment")),
    )

    # [Hidden Failure] Validation rejects a category mismatch without mutating the store.
    before = store.snapshot()
    try:
        store.add_suggestion("verification", _draft("Wrong category", category="experiment"))
    except ValueError:
        rejected = True
    else:
        rejected = False
    results.check(
        "category mismatch leaves state unchanged", rejected and store.snapshot() == before
    )

    # [Silent Failure] Removing one item preserves the other item's stable ID and order.
    store.remove_suggestion("idea-001")
    results.check(
        "removal does not renumber remaining IDs",
        tuple(i.id for i in store.snapshot()) == ("idea-002",),
    )

    # [Hidden Assumption] Unknown evidence is rejected even when the draft shape is valid.
    try:
        store.add_suggestion(
            "verification",
            _draft("Unknown evidence").model_copy(update={"evidence_refs": ("missing",)}),
        )
    except ValueError:
        unknown_evidence = True
    else:
        unknown_evidence = False
    results.check("unknown evidence is rejected", unknown_evidence)

    # [Hidden Failure] Working mutations are discarded when the transaction is not committed.
    working = store.working_copy()
    working.remove_suggestion("idea-002")
    results.check(
        "uncommitted working copy cannot remove active state", store.snapshot()[0].id == "idea-002"
    )

    # [Edge Case] More-suggestions guidance reports a bounded capacity and category gap.
    results.check(
        "more-suggestions returns bounded guidance",
        "Missing categories" in store.more_suggestions(),
    )
    return results.finish()


if __name__ == "__main__":
    raise SystemExit(main())
