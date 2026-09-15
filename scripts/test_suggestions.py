"""Offline verification for the SDK-backed suggestion workflow.

The fake lives at the local SDK adapter boundary, so the tests exercise request
validation, context placement, structured artifacts, critique decisions, curation,
extra-compute fan-out, and deterministic handoff rendering without credentials.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from vidbyte_cli.commands.agents.suggestion.request_builder import (  # noqa: E402
    SuggestionRequestBuilder,
    SuggestionRunInput,
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
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.services.suggestions.store import SuggestionStore  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    MAX_CONTEXT_CHARS,
    SUGGESTIONS_HANDOFF_KIND,
    SUGGESTIONS_RESULT_KIND,
    ContextManifestEntry,
    CritiqueConfidence,
    CritiqueEvidenceCheck,
    CritiqueVerdict,
    SuggestionCandidateBatch,
    SuggestionCompletion,
    SuggestionContextItem,
    SuggestionContextPrimitive,
    SuggestionCritique,
    SuggestionCritiqueArtifact,
    SuggestionDraft,
    SuggestionRequest,
    SuggestionSettings,
)


class Results:
    """Prints one result per assertion and decides the process status."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
        else:
            self.failed += 1
            suffix = f" - {detail}" if detail else ""
            print(f"FAIL: {name}{suffix}", file=sys.stderr)

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return int(self.failed > 0)


@dataclass
class FakeReply:
    structured: Any
    codex: Any = None


class FakeAgent:
    """Returns typed artifacts while recording the context used for each turn."""

    def __init__(self, sdk: FakeSdk, settings: SuggestionAgentSettingsInput) -> None:
        self.sdk = sdk
        self.settings = settings

    async def arun(self, request: SuggestionTextInput) -> FakeReply:
        self.sdk.turns.append((self.settings, request.prompt))
        structured = self.sdk.next_artifact(self.settings, request.prompt)
        usage = SimpleNamespace(last_usage=SimpleNamespace(total_tokens=10))
        return FakeReply(structured=structured, codex=usage)


class FakeSdk:
    """A typed fake for the SuggestionSdk methods used by SuggestionService."""

    def __init__(
        self,
        *,
        revision: bool = False,
        extra_compute: bool = False,
        curation_failure: bool = False,
        incomplete_curation: bool = False,
    ) -> None:
        self.revision = revision
        self.extra_compute = extra_compute
        self.curation_failure = curation_failure
        self.incomplete_curation = incomplete_curation
        self.settings: list[SuggestionAgentSettingsInput] = []
        self.turns: list[tuple[SuggestionAgentSettingsInput, str]] = []
        self.generator_calls = 0
        self.critic_calls = 0
        self.curation_calls = 0

    def agent_settings(self, request: SuggestionAgentSettingsInput) -> SuggestionAgentSettingsInput:
        self.settings.append(request)
        return request

    def agent(self, settings: SuggestionAgentSettingsInput) -> FakeAgent:
        return FakeAgent(self, settings)

    def run_input(self, request: SuggestionTextInput) -> SuggestionTextInput:
        if not isinstance(request, SuggestionTextInput):
            raise TypeError("fake received an untyped SDK input")
        return request

    def next_artifact(self, settings: SuggestionAgentSettingsInput, prompt: str) -> Any:
        if settings.role == "critic":
            self.critic_calls += 1
            ids = self._candidate_ids(settings.context.candidate_handoffs)
            critiques = []
            for index, idea_id in enumerate(ids):
                if self.revision and self.critic_calls == 1 and index == 0:
                    critiques.append(
                        _critique(
                            idea_id,
                            verdict=CritiqueVerdict.REVISE,
                            fix="Clarify the first action without changing the evidence.",
                            preserve=("title", "primary_category", "considerations"),
                        )
                    )
                else:
                    critiques.append(_critique(idea_id))
            return SuggestionCritiqueArtifact(critiques=tuple(critiques))

        self.generator_calls += 1
        if settings.tools:
            self.curation_calls += 1
            if self.curation_failure:
                raise RuntimeError("simulated curation provider failure")
            if self.incomplete_curation:
                return SuggestionCompletion(completed=False, summary="Could not finish.")
            if self.curation_calls > 1:
                return SuggestionCompletion(summary="The active slate is already useful.")
            draft = _draft(
                "verification",
                idea_id="idea-001",
                title="Repaired verification action",
                first_action="Clarify the first action and run the smallest safe check.",
                evidence_refs=tuple(item.ref for item in settings.context.items[:1]),
            )
            settings.tools[0]("verification", draft)
            settings.tools[2]()
            return SuggestionCompletion(summary="Applied the critic feedback through store tools.")
        categories = _categories_from_context(settings.context.selected_categories)
        count = 2 if self.extra_compute else 4
        return SuggestionCandidateBatch(
            ideas=tuple(
                _draft(
                    categories[index % len(categories)],
                    title=f"{categories[index % len(categories)]} action {index}",
                    evidence_refs=tuple(item.ref for item in settings.context.items[:1]),
                )
                for index in range(count)
            )
        )

    def _candidate_ids(self, handoffs: str) -> tuple[str, ...]:
        if not handoffs:
            return ()
        return tuple(item["id"] for item in json.loads(handoffs))


def _categories_from_context(text: str) -> tuple[str, ...]:
    headings = tuple(
        line.removeprefix("# ").strip().lower().replace(" ", "_")
        for line in text.splitlines()
        if line.startswith("# ")
    )
    return headings or ("verification",)


def _critique(
    idea_id: str,
    *,
    verdict: CritiqueVerdict = CritiqueVerdict.KEEP,
    fix: str = "",
    preserve: tuple[str, ...] = (),
) -> SuggestionCritique:
    return SuggestionCritique(
        idea_id=idea_id,
        verdict=verdict,
        confidence=CritiqueConfidence.HIGH,
        evidence_check=CritiqueEvidenceCheck.SUPPORTED,
        fix_instruction=fix,
        preserve=preserve,
        review_summary=f"Reviewed {idea_id} with no unsupported claim.",
    )


def _draft(
    category: str,
    *,
    idea_id: str | None = None,
    title: str = "A bounded next action",
    first_action: str = "Inspect the current state and record the smallest useful check.",
    evidence_refs: tuple[str, ...] = (),
) -> SuggestionDraft:
    return SuggestionDraft(
        idea_id=idea_id,
        title=title,
        summary="Take one bounded action that produces useful evidence for the stated goal.",
        primary_category=category,
        why_now="The current state is available for a focused check.",
        expected_benefit="The next decision becomes easier to make.",
        evidence_refs=evidence_refs,
        assumptions=("The caller can inspect the relevant state.",),
        dependencies=("The current task remains available.",),
        first_action=first_action,
        suggested_actions=(first_action, "Record the result and decide the next bounded move."),
        decision_points=("Continue only if the check changes the decision.",),
        considerations=tuple(f"Material consideration {index}." for index in range(1, 9)),
        completion_criteria="A dated result is recorded and the next decision is explicit.",
        effort_estimate="Small bounded check",
    )


def _item(
    ref: str = "ctx-001", content: str = "The caller supplied this evidence."
) -> SuggestionContextItem:
    return SuggestionContextItem(
        ref=ref,
        kind="trajectory",
        label="trajectory",
        description=(
            "This record explains the current direction and why it can affect the next action."
        ),
        content=content,
        source="flag:trajectory",
    )


def _request(
    *,
    count: int = 4,
    categories: tuple[str, ...] = ("verification", "experiment"),
    extra_compute: bool = False,
    rounds: int = 1,
    items: tuple[SuggestionContextItem, ...] = (),
) -> SuggestionRequest:
    goal = "Ship the first suggestion agent release"
    manifest = tuple(
        ContextManifestEntry(
            ref=item.ref,
            kind=item.kind,
            source=item.source,
            chars=len(item.content),
            sha256=hashlib.sha256(item.content.encode()).hexdigest()[:16],
        )
        for item in items
    )
    context = SuggestionContextPrimitive(
        goal=goal,
        description="This context defines the caller state used for one bounded suggestion run.",
        items=items,
    )
    return SuggestionRequest(
        goal=goal,
        context=context,
        context_manifest=manifest,
        settings=SuggestionSettings(
            requested_count=count,
            categories=categories,
            extra_compute=extra_compute,
            rounds=rounds,
        ),
    )


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    import os

    environment = dict(os.environ)
    source = str(REPOSITORY_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
    return subprocess.run(
        [sys.executable, "-m", "vidbyte_cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


class SuggestionSuite:
    """Covers each externally visible contract with provider-free execution."""

    def __init__(self, results: Results) -> None:
        self.results = results

    def run(self) -> None:
        self.check_categories_and_prompts()
        self.check_request_boundary()
        self.check_sdk_context_boundary()
        self.check_generation_and_revision()
        self.check_extra_compute()
        self.check_store_contract()
        self.check_context_limits_and_handoff()
        self.check_cli_contracts()

    def check_categories_and_prompts(self) -> None:
        results = self.results
        registry = SuggestionCategories()
        results.check("registry exposes all 31 categories", len(registry.ids()) == 31)
        results.check(
            "category identifiers and prompt assets are one-to-one",
            len({item.prompt_name for item in registry.definitions()}) == 31
            and all(
                registry.category_prompt_exists(item.prompt_name) for item in registry.definitions()
            ),
        )
        selected = registry.prompt_section(("verification", "experiment"))
        results.check(
            "selected categories map directly to selected prompt assets",
            selected.startswith("# Verification")
            and "# Experiment" in selected
            and "# Continuation" not in selected,
        )
        prompts = SuggestionPrompts()
        results.check(
            "generator critic and curation prompts are distinct and loaded",
            len(prompts.generator_system()) > 100
            and len(prompts.critic_system()) > 100
            and len(prompts.curator_turn("goal", 2)) > 100,
        )

    def check_request_boundary(self) -> None:
        results = self.results
        built = SuggestionRequestBuilder().build(
            {
                "goal": "Build through the dedicated request collaborator",
                "count": 2,
                "categories": ("verification", "experiment"),
                "mistakes": ("bad merge | stale base | use current main",),
                "extra_compute": True,
            }
        )
        results.check(
            "request builder emits one strict settings object",
            built.settings.categories == ("verification", "experiment")
            and built.settings.extra_compute
            and built.context_items[0].kind == "mistakes",
        )
        context_text = built.context.to_context_text()
        results.check(
            "agent context contains values without caller-facing help prose",
            "bad merge | stale base | use current main" in context_text
            and "Caller-supplied context value." not in context_text,
        )
        results.check(
            "context primitive includes the selected category block",
            "<Selected Categories>" in context_text and "# Verification" in context_text,
        )
        rejected = _run_cli(["agents", "suggest", "run", "--goal", "x", "--input", "request.json"])
        results.check("run no longer accepts a JSON input file", rejected.returncode == 2)
        bad_count = _run_cli(["agents", "suggest", "run", "--goal", "x", "--count", "1"])
        results.check("count below 2 fails before model calls", bad_count.returncode == 2)
        try:
            SuggestionRunInput(goal="x", count=1)
        except ValueError:
            strict_rejection = True
        else:
            strict_rejection = False
        results.check("request dataclass rejects invalid values at construction", strict_rejection)

    def check_sdk_context_boundary(self) -> None:
        results = self.results
        context = _request().context
        sdk = SuggestionSdk.load()
        generator = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role="generator",
                system_prompt="Generator system prompt.",
                context=context,
                output_schema=SuggestionCandidateBatch,
                provider="openai",
            )
        )
        critic = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role="critic",
                system_prompt="Critic system prompt.",
                context=context,
                output_schema=SuggestionCritiqueArtifact,
            )
        )
        results.check(
            "generator and critic receive independent managed context windows",
            generator.context_manager is not critic.context_manager
            and generator.context_manager.get_by_id("suggestion-context:request") is context
            and critic.context_manager.get_by_id("suggestion-context:request") is context,
        )
        results.check(
            "SDK settings enforce the read-only provider boundary",
            generator.codex.thread.model_provider == "openai"
            and generator.codex.thread.model == ""
            and str(generator.codex.thread.sandbox) in ("CodexSandbox.READ_ONLY", "read-only")
            and str(generator.codex.thread.approval_mode)
            in ("CodexApprovalMode.DENY_ALL", "deny_all"),
        )
        results.check(
            "SDK text input is typed",
            isinstance(sdk.run_input(SuggestionTextInput("Review candidates.")), object),
        )

    def check_generation_and_revision(self) -> None:
        results = self.results
        fake = FakeSdk(revision=True)
        result = SuggestionService(sdk=fake).run(_request(rounds=2, items=(_item(),)))
        results.check(
            "generated ideas survive independent critique with deterministic handoffs",
            result.returned_count == 4
            and all(idea.handoff.idea_id == idea.id for idea in result.ideas)
            and all(idea.evidence_refs == ("ctx-001",) for idea in result.ideas),
        )
        revised = next((idea for idea in result.ideas if idea.id == "idea-001"), None)
        results.check(
            "curation tool update preserves identity and increments revision",
            revised is not None
            and revised.revision == 2
            and revised.title == "Repaired verification action",
        )
        results.check(
            "critic context carries candidate handoffs and selected categories",
            any(
                settings.role == "critic"
                and "<Candidate Handoffs>" in settings.context.to_context_text()
                and "<Selected Categories>" in settings.context.to_context_text()
                for settings, _ in fake.turns
            ),
        )
        dry_request = _request().model_copy(
            update={"settings": SuggestionSettings(requested_count=4, dry_run=True)}
        )
        dry_fake = FakeSdk()
        dry = SuggestionService(sdk=dry_fake).run(dry_request)
        results.check(
            "dry run never constructs an agent", dry.returned_count == 0 and not dry_fake.turns
        )
        failed = SuggestionService(sdk=FakeSdk(curation_failure=True)).run(
            _request(rounds=2, items=(_item(),))
        )
        results.check(
            "curation provider failure returns the committed snapshot",
            failed.stop_reason.value == "provider_failed"
            and failed.returned_count == 4
            and bool(failed.warnings),
        )
        incomplete = SuggestionService(sdk=FakeSdk(incomplete_curation=True)).run(
            _request(rounds=2, items=(_item(),))
        )
        results.check(
            "incomplete curation receipts are surfaced as partial results",
            incomplete.stop_reason.value == "provider_failed"
            and incomplete.returned_count == 4
            and bool(incomplete.warnings),
        )

    def check_extra_compute(self) -> None:
        results = self.results
        fake = FakeSdk(extra_compute=True)
        result = SuggestionService(sdk=fake).run(_request(extra_compute=True, count=2))
        generator_contexts = [
            settings.context.selected_categories
            for settings, _ in fake.turns
            if settings.role == "generator" and not settings.tools
        ]
        results.check(
            "extra compute fans out one generator context per selected category",
            len(generator_contexts) == 2
            and all(text.count("\n") > 2 for text in generator_contexts)
            and "# Verification" in generator_contexts[0]
            and "# Experiment" in generator_contexts[1],
        )
        results.check(
            "extra compute still returns the requested bounded slate", result.returned_count == 2
        )

    def check_store_contract(self) -> None:
        results = self.results
        request = _request(items=(_item(),))
        store = SuggestionStore(request, ("verification", "experiment"))
        idea = SuggestionService(sdk=FakeSdk())._ideas_from_drafts(
            SuggestionCandidateBatch(ideas=(_draft("verification", evidence_refs=("ctx-001",)),)),
            request,
        )[0]
        store.seed((idea,))
        message = store.add_suggestion(
            "verification",
            _draft(
                "verification",
                idea_id=idea.id,
                title="Updated store action",
                evidence_refs=("ctx-001",),
            ),
        )
        results.check(
            "store tools expose typed stable mutations",
            "idea-001" in message and store.snapshot()[0].revision == 2,
        )
        removed = store.remove_suggestion("idea-001")
        results.check("store removal uses stable IDs", "Removed suggestion" in removed)
        results.check(
            "store removal does not renumber unknown IDs",
            "No active suggestion" in store.remove_suggestion("idea-999"),
        )
        results.check(
            "store working copies do not mutate committed state",
            store.working_copy().snapshot() == store.snapshot(),
        )

    def check_context_limits_and_handoff(self) -> None:
        results = self.results
        snapshot = SuggestionContextBuilder().build(
            {"trajectory": ("x" * (MAX_CONTEXT_CHARS + 10),)}, ()
        )
        results.check(
            "oversized flag context is truncated and manifested",
            len(snapshot.items[0].content) == MAX_CONTEXT_CHARS
            and snapshot.manifest[0].status == "truncated"
            and snapshot.manifest[0].chars == MAX_CONTEXT_CHARS,
        )
        builder = SuggestionHandoffBuilder()
        result = SuggestionService(sdk=FakeSdk()).run(_request(items=(_item(),)))
        packet = builder.build(result.ideas[0], _request(items=(_item(),)))
        rendered = builder.render_prompt(packet)
        results.check(
            "handoff is deterministic and does not grant authority",
            packet.authority == "not_granted_by_this_handoff"
            and packet.evidence[0].ref == "ctx-001"
            and packet.evidence[0].content == _item().content
            and rendered == builder.render_prompt(packet),
        )
        results.check(
            "stable output envelope constants remain versioned",
            SUGGESTIONS_HANDOFF_KIND == "suggestions.handoff"
            and SUGGESTIONS_RESULT_KIND == "suggestions.result",
        )

    def check_cli_contracts(self) -> None:
        results = self.results
        help_result = _run_cli(["agents", "suggest", "run", "--help"])
        results.check(
            "expanded context and extra compute controls are visible",
            help_result.returncode == 0
            and "--extra-compute" in help_result.stdout
            and "--trajectory" in help_result.stdout
            and "--files" in help_result.stdout
            and "--context-file" not in help_result.stdout
            and "--handoff-file" not in help_result.stdout
            and "--artifact-file" not in help_result.stdout
            and "--input" not in help_result.stdout,
        )
        categories = _run_cli(["--json", "agents", "suggest", "categories", "--view-all"])
        try:
            document = json.loads(categories.stdout)
            visible = document.get("data", {}).get("categories", [])
        except json.JSONDecodeError:
            visible = []
        results.check(
            "category listing works without credentials",
            categories.returncode == 0 and len(visible) == 31,
        )
        detail = _run_cli(["--json", "agents", "suggest", "categories", "--view", "feedback"])
        try:
            detail_document = json.loads(detail.stdout)
            detail_item = (detail_document.get("data", {}).get("categories", []) or [{}])[0]
        except json.JSONDecodeError:
            detail_item = {}
        results.check(
            "one category can be expanded without a provider",
            detail.returncode == 0
            and detail_item.get("id") == "feedback"
            and "Things to consider" in detail_item.get("prompt", ""),
        )
        dry = _run_cli(["--json", "agents", "suggest", "run", "--goal", "Dry goal", "--dry-run"])
        try:
            dry_document = json.loads(dry.stdout)
        except json.JSONDecodeError:
            dry_document = {}
        results.check(
            "dry-run produces a results-only envelope without a model",
            dry.returncode == 0
            and dry_document.get("kind") == SUGGESTIONS_RESULT_KIND
            and dry_document.get("data", {}).get("stop_reason") == "dry_run",
        )


def main() -> int:
    results = Results()
    SuggestionSuite(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
