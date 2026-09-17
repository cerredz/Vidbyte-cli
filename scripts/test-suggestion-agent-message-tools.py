"""Offline verification for role-specific suggestion-agent message tools."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from vidbyte_cli.services.suggestions.message_tools import SuggestionMessageTools  # noqa: E402
from vidbyte_cli.services.suggestions.sdk import (  # noqa: E402
    SuggestionAgentSession,
    SuggestionAgentSettingsInput,
    SuggestionTextInput,
)
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.types.attachments import AttachmentBundle  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    MAX_AGENT_MESSAGE_CHARS,
    ContextManifestEntry,
    CriticObservationKind,
    StopReason,
    SuggestionAgentContext,
    SuggestionCandidateBatch,
    SuggestionContextItem,
    SuggestionContextPrimitive,
    SuggestionCriticContext,
    SuggestionCriticContextPrimitive,
    SuggestionCriticObservation,
    SuggestionDraft,
    SuggestionRequest,
    SuggestionSettings,
)


class Results:
    """Prints one result per assertion and returns a process status."""

    def __init__(self) -> None:
        # Tracks the final executable verification summary.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        # Prints a stable PASS or FAIL record for one test case.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
        else:
            self.failed += 1
            suffix = f" - {detail}" if detail else ""
            print(f"FAIL: {name}{suffix}", file=sys.stderr)

    def summary(self) -> int:
        # Prints the aggregate result and returns non-zero when any case failed.
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return int(self.failed > 0)


@dataclass
class FakeReply:
    """Carries the structured artifact shape consumed by SuggestionService."""

    structured: Any
    codex: Any = None


class FakeAgent:
    """Calls one configured message tool and returns a typed stage artifact."""

    def __init__(self, sdk: FakeSdk, settings: SuggestionAgentSettingsInput) -> None:
        # Keeps the fake bound to the settings the service constructed.
        self._sdk = sdk
        self.settings = settings
        self.thread_id = f"thread-{id(self)}"
        self.last_candidates: tuple[SuggestionDraft, ...] = ()

    async def arun(self, request: SuggestionTextInput) -> FakeReply:
        # Simulates generation, critique, and refinement without a provider.
        _ = request
        if self.settings.role == "critic":
            if self.settings.tools:
                await self.settings.tools[0]("Reconsider overlap between the first candidates.")
            return FakeReply(self._sdk.critic_context(), self._sdk.usage())
        if self._sdk.parent_mode:
            if self.settings.tools:
                await self.settings.tools[0]("What deadline should these ideas satisfy?")
            return FakeReply(None, self._sdk.usage())
        if self.last_candidates:
            return FakeReply(
                SuggestionCandidateBatch(ideas=self.last_candidates), self._sdk.usage()
            )
        candidates = (
            self._sdk.draft("verification", "First bounded action"),
            self._sdk.draft("experiment", "Second bounded action"),
        )
        self.last_candidates = candidates
        return FakeReply(SuggestionCandidateBatch(ideas=candidates), self._sdk.usage())


class FakeSdk:
    """Captures role-specific settings and context placement for service tests."""

    def __init__(self, *, parent_mode: bool = False) -> None:
        # Selects whether the generator emits a parent request during its first turn.
        self.parent_mode = parent_mode
        self.settings: list[SuggestionAgentSettingsInput] = []
        self.critic_primitives: list[SuggestionCriticContextPrimitive] = []
        self.session: SuggestionAgentSession | None = None

    def agent_settings(
        self, settings: SuggestionAgentSettingsInput
    ) -> SuggestionAgentSettingsInput:
        # Records one independent agent construction.
        self.settings.append(settings)
        return settings

    def agent(self, settings: SuggestionAgentSettingsInput) -> FakeAgent:
        # Builds a fresh fake critic or fan-out agent.
        return FakeAgent(self, settings)

    def agent_session(self, settings: SuggestionAgentSettingsInput) -> SuggestionAgentSession:
        # Builds the persistent generator session and records its tools.
        self.settings.append(settings)
        self.session = SuggestionAgentSession(FakeAgent(self, settings), SimpleNamespace())
        return self.session

    def place_critic_context(
        self, session: SuggestionAgentSession, context: SuggestionCriticContextPrimitive
    ) -> None:
        # Captures the context the service will send to the next generator turn.
        _ = session
        self.critic_primitives.append(context)

    def replace_stage_context(
        self, session: SuggestionAgentSession, context: SuggestionAgentContext
    ) -> None:
        # Records no behavior because the message assertions target critic context.
        _ = (session, context)

    def run_input(self, request: SuggestionTextInput) -> SuggestionTextInput:
        # Preserves the typed input boundary without invoking a provider.
        return request

    def usage(self) -> Any:
        # Supplies the minimum usage shape the service records.
        return SimpleNamespace(last_usage=SimpleNamespace(total_tokens=1))

    def critic_context(self) -> SuggestionCriticContext:
        # Returns a valid whole-slate critic artifact after sending guidance.
        return SuggestionCriticContext(
            overall_assessment="The slate is distinct enough to refine.",
            strengths_to_preserve=("The actions are bounded.",),
            observations=(
                SuggestionCriticObservation(
                    kind=CriticObservationKind.ACTIONABILITY,
                    signal="The first action should name its smallest check.",
                    implication="A smaller check improves execution clarity.",
                ),
            ),
        )

    def draft(self, category: str, title: str) -> SuggestionDraft:
        # Builds one schema-valid candidate for the fake generator.
        action = f"Start the {title.lower()}."
        return SuggestionDraft(
            title=title,
            summary="Take one bounded action that produces useful evidence.",
            primary_category=category,
            why_now="The current state supports a focused check.",
            expected_benefit="The next decision becomes easier.",
            assumptions=("The supplied state is accurate.",),
            dependencies=("The goal remains active.",),
            first_action=action,
            suggested_actions=(action, "Record the result."),
            considerations=tuple(f"Consideration {index}." for index in range(1, 9)),
            completion_criteria="A dated result is recorded.",
            effort_estimate="Small bounded check",
        )


class MessageToolVerification:
    """Runs direct tool, context, and workflow routing checks."""

    def __init__(self, results: Results) -> None:
        # Shares the executable assertion reporter across all cases.
        self.results = results

    def run(self) -> None:
        # Executes every feature case in a deterministic offline order.
        self.check_direct_tools()
        self.check_context_rendering()
        self.check_critic_routing()
        self.check_parent_routing()

    def check_direct_tools(self) -> None:
        # Verifies names, descriptions, stop acknowledgements, validation, and isolation.
        tools = SuggestionMessageTools()
        generator_tool = tools.generator_tools()[0]
        critic_tool = tools.critic_tools()[0]
        parent_text = asyncio.run(generator_tool("Need the caller's deadline."))
        critic_text = asyncio.run(critic_tool("Reconsider the overlap."))
        self.results.check(
            "tools have role-specific names and stop descriptions",
            generator_tool.__name__ == "message_parent"
            and critic_tool.__name__ == "message_generator"
            and "parent agent" in (generator_tool.__doc__ or "")
            and "generator agent" in (critic_tool.__doc__ or "")
            and "stop" in (generator_tool.__doc__ or "").lower()
            and "stop" in (critic_tool.__doc__ or "").lower()
            and "parent agent" in parent_text
            and "generator agent" in critic_text
            and "stop" in parent_text.lower()
            and "stop" in critic_text.lower(),
        )
        self.results.check(
            "valid messages route to their intended recipients",
            tools.parent_messages() == ("Need the caller's deadline.",)
            and tools.drain_generator_messages() == ("Reconsider the overlap.",)
            and tools.drain_generator_messages() == (),
        )
        invalid = False
        try:
            asyncio.run(generator_tool("   "))
        except ValueError:
            invalid = True
        self.results.check(
            "empty messages fail without mutation",
            invalid and tools.parent_messages() == ("Need the caller's deadline.",),
        )
        oversized = False
        try:
            asyncio.run(critic_tool("x" * (MAX_AGENT_MESSAGE_CHARS + 1)))
        except ValueError:
            oversized = True
        self.results.check("overlong messages fail at the tool boundary", oversized)

    def check_context_rendering(self) -> None:
        # Verifies critic messages render after the typed signal in stable order.
        context = SuggestionCriticContext(
            overall_assessment="The slate is useful.",
        )
        primitive = SuggestionCriticContextPrimitive(context, ("First note.", "Second note."))
        rendered = primitive.to_context_text()
        self.results.check(
            "critic messages render in order after the structured signal",
            rendered.index("First note.") < rendered.index("Second note.")
            and rendered.index("Messages from critic") < rendered.index("First note."),
        )

    def check_critic_routing(self) -> None:
        # Verifies critic guidance reaches the next generator context without nesting.
        sdk = FakeSdk()
        result = SuggestionService(sdk=sdk).run(self.request())
        critic_settings = next(settings for settings in sdk.settings if settings.role == "critic")
        generator_settings = next(
            settings for settings in sdk.settings if settings.role == "generator"
        )
        self.results.check(
            "critic and generator receive only their own message tools",
            critic_settings.tools[0].__name__ == "message_generator"
            and generator_settings.tools[0].__name__ == "message_parent",
        )
        self.results.check(
            "critic message reaches the generator context",
            bool(sdk.critic_primitives)
            and sdk.critic_primitives[0].messages
            == ("Reconsider overlap between the first candidates.",)
            and result.stop_reason
            in (StopReason.COMPLETED, StopReason.COUNT_SHORTFALL, StopReason.ROUND_LIMIT),
        )

    def check_parent_routing(self) -> None:
        # Verifies a generator stop request becomes a typed parent-input result.
        sdk = FakeSdk(parent_mode=True)
        result = SuggestionService(sdk=sdk).run(self.request())
        self.results.check(
            "parent message stops generation with a typed result",
            result.status.value == "needs_input"
            and result.stop_reason is StopReason.PARENT_MESSAGE
            and result.agent_messages == ("What deadline should these ideas satisfy?",),
        )

    def request(self) -> SuggestionRequest:
        # Builds the smallest valid request shared by workflow cases.
        item = SuggestionContextItem(
            ref="ctx-001",
            kind="trajectory",
            label="trajectory",
            description="Current direction.",
            content="The current direction is available.",
            source="test",
        )
        context = SuggestionContextPrimitive(
            goal="Ship the suggestion agent",
            description="Bounded test context.",
            items=(item,),
        )
        manifest = (
            ContextManifestEntry(
                ref=item.ref,
                kind=item.kind,
                source=item.source,
                chars=len(item.content),
                sha256=hashlib.sha256(item.content.encode()).hexdigest()[:16],
            ),
        )
        return SuggestionRequest(
            goal=context.goal,
            context=context,
            context_manifest=manifest,
            settings=SuggestionSettings(
                requested_count=2,
                categories=("verification", "experiment"),
                rounds=1,
            ),
            attachments=AttachmentBundle(),
        )


def main() -> int:
    # Runs the feature verification and returns its process status.
    results = Results()
    MessageToolVerification(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
