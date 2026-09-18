"""Offline verification for the suggestion agents' stop-and-message tools.

The SDK checks build real `CodexHarnessAgentSettings` and run the tools through
the SDK's own Codex tool translator. The workflow checks fake only the agent turn,
so they exercise the stop signal, turn cancellation, message routing into the
generator's thread, the parent result, and the caller's --max-messages budget.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from test_suggestions import Results, _draft, _item, _request  # noqa: E402

from vidbyte_cli.commands.agents.suggestion.request_builder import (  # noqa: E402
    SuggestionRunInput,
)
from vidbyte_cli.services.suggestions.message_tools import SuggestionMessageTool  # noqa: E402
from vidbyte_cli.services.suggestions.prompts.library import SuggestionPrompts  # noqa: E402
from vidbyte_cli.services.suggestions.sdk import (  # noqa: E402
    SuggestionAgentSettingsInput,
    SuggestionSdk,
    SuggestionTextInput,
)
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    MAX_AGENT_MESSAGE_CHARS,
    RunStatus,
    StopReason,
    SuggestionAgentContext,
    SuggestionCandidateBatch,
    SuggestionCriticHandoff,
)

_SENTENCE = re.compile(r"[.!?](?:\s|$)")


class MessagingAgent:
    """Answers with a typed artifact, or calls its message tool and never finishes."""

    def __init__(self, sdk: MessagingSdk, settings: SuggestionAgentSettingsInput) -> None:
        self.sdk = sdk
        self.settings = settings
        self.prompts: list[str] = []
        self.cancelled = False

    async def arun(self, request: SuggestionTextInput) -> Any:
        self.prompts.append(request.prompt)
        message = self.sdk.message_for(self.settings)
        if message is not None:
            tool = self.settings.tools[0]
            tool.deliver(message)
            # A model that ignores the stop instruction keeps running until it is cancelled.
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        usage = SimpleNamespace(last_usage=SimpleNamespace(total_tokens=10))
        return SimpleNamespace(structured=self.sdk.artifact(self.settings), codex=usage)


class MessagingSdk:
    """Fake SDK whose agents send a message on chosen turns."""

    def __init__(self, *, parent: str | None = None, critic: str | None = None) -> None:
        self.parent = parent
        self.critic = critic
        self.agents: list[MessagingAgent] = []

    def agent_settings(self, request: SuggestionAgentSettingsInput) -> SuggestionAgentSettingsInput:
        return request

    def agent(self, settings: SuggestionAgentSettingsInput) -> MessagingAgent:
        agent = MessagingAgent(self, settings)
        self.agents.append(agent)
        return agent

    def run_input(self, request: SuggestionTextInput) -> SuggestionTextInput:
        return request

    def message_for(self, settings: SuggestionAgentSettingsInput) -> str | None:
        # Messages are sent only through a tool the service actually registered.
        if not settings.tools:
            return None
        return self.parent if settings.role == "generator" else self.critic

    def artifact(self, settings: SuggestionAgentSettingsInput) -> Any:
        if settings.role == "critic":
            return SuggestionCriticHandoff(handoff="Full critic review of the slate.")
        return SuggestionCandidateBatch(
            ideas=tuple(
                _draft(
                    "verification", title=f"Verification action {index}", evidence_refs=("ctx-001",)
                )
                for index in range(4)
            )
        )

    def generators(self) -> list[MessagingAgent]:
        return [agent for agent in self.agents if agent.settings.role == "generator"]

    def critics(self) -> list[MessagingAgent]:
        return [agent for agent in self.agents if agent.settings.role == "critic"]


def _settings_with(request: Any, **updates: Any) -> Any:
    return request.model_copy(update={"settings": request.settings.model_copy(update=updates)})


class MessageToolSuite:
    """Covers the SDK tool contract and each workflow path a message can take."""

    def __init__(self, results: Results) -> None:
        self.results = results
        self.prompts = SuggestionPrompts()

    def run(self) -> None:
        self.check_descriptions()
        self.check_deliver_contract()
        asyncio.run(self.check_sdk_tool())
        self.check_parent_message()
        self.check_critic_message()
        self.check_message_budget()
        self.check_cli_setting()

    def check_descriptions(self) -> None:
        check = self.results.check
        for name in ("message_parent", "message_generator"):
            sentences = len(_SENTENCE.findall(self.prompts.message_tool(name)))
            check(f"{name} description has 6-8 sentences", 6 <= sentences <= 8, str(sentences))
        check(
            "parent description names the parent agent",
            "parent agent" in self.prompts.message_tool("message_parent"),
        )
        check(
            "generator description names the generator agent",
            "generator agent" in self.prompts.message_tool("message_generator"),
        )

    def check_deliver_contract(self) -> None:
        check = self.results.check
        tool = SuggestionMessageTool("message_parent", self.prompts)
        for bad in ("", "   ", 3, "x" * (MAX_AGENT_MESSAGE_CHARS + 1)):
            try:
                tool.deliver(bad)
                rejected = False
            except ValueError:
                rejected = True
            check(f"deliver rejects {type(bad).__name__} of length {len(str(bad))}", rejected)
        check("a rejected message does not stop the turn", not tool.stopped.is_set())
        receipt = tool.deliver("  Which release is in scope?  ")
        tool.deliver("A later message.")
        check("deliver records the stripped message", tool.message == "Which release is in scope?")
        check("deliver signals the stop", tool.stopped.is_set())
        check("deliver returns the stop receipt", "Stop now" in receipt)

    async def check_sdk_tool(self) -> None:
        check = self.results.check
        try:
            sdk = SuggestionSdk.load()
            from vidbyte.agents.codex.tools import CodexToolTranslator
            from vidbyte.tools import ToolCall, ToolStatus
        except Exception as error:  # pragma: no cover - reported as a failed check
            check("SDK tool surface loads", False, repr(error))
            return
        tool = SuggestionMessageTool("message_generator", self.prompts)
        settings = sdk.agent_settings(
            SuggestionAgentSettingsInput(
                role="critic",
                system_prompt="Review the slate.",
                context=SuggestionAgentContext.for_stage(_request().context, "# Verification", ()),
                output_schema=SuggestionCriticHandoff,
                tools=(tool,),
            )
        )
        bridge = CodexToolTranslator.translate(settings)
        declared = bridge.dynamic_tools[0] if bridge else {}
        check("Codex registers the message tool", declared.get("name") == "message_generator")
        check(
            "Codex sees the authored description",
            declared.get("description") == self.prompts.message_tool("message_generator"),
        )
        check(
            "Codex sees one required message argument",
            declared.get("inputSchema", {}).get("required") == ["message"],
            str(declared.get("inputSchema")),
        )
        sdk_tool = settings.tools[0]
        empty = await sdk_tool.execute(ToolCall(tool_name="message_generator", arguments={}))
        check("an invalid call returns an error to the model", empty.status == ToolStatus.ERROR)
        sent = await sdk_tool.execute(
            ToolCall(
                tool_name="message_generator", arguments={"message": "Every idea misreads ctx-001."}
            )
        )
        check("a valid call succeeds", sent.status == ToolStatus.SUCCESS)
        check("a valid call delivers the message", tool.message == "Every idea misreads ctx-001.")

    def check_parent_message(self) -> None:
        check = self.results.check
        sdk = MessagingSdk(parent="Which of the two release dates in ctx-001 is current?")
        request = _request(items=(_item(),), rounds=2)
        result = SuggestionService(sdk).run(request)
        generator = sdk.generators()[0]
        check("parent message returns needs_input", result.status is RunStatus.NEEDS_INPUT)
        check("parent message stop reason", result.stop_reason is StopReason.PARENT_MESSAGE)
        check("parent message is in the result", result.parent_message == sdk.parent)
        check("parent message returns no ideas", result.ideas == ())
        check("the generator's turn was cancelled", generator.cancelled)
        check("no critic runs after a parent message", not sdk.critics())
        check("the stopped turn is counted", result.usage.get("generation_calls") == 1)

    def check_critic_message(self) -> None:
        check = self.results.check
        sdk = MessagingSdk(critic="The whole slate ignores the freeze in ctx-001.")
        result = SuggestionService(sdk).run(_request(items=(_item(),), rounds=1))
        generators = sdk.generators()
        critic = sdk.critics()[0]
        check("critic message keeps one generator thread", len(generators) == 1)
        check("the critic's turn was cancelled", critic.cancelled)
        check(
            "the message is the generator's next turn",
            len(generators[0].prompts) == 2 and sdk.critic in generators[0].prompts[1],
        )
        check(
            "the next turn uses the critic message prompt",
            "# Critic message" in generators[0].prompts[1],
        )
        check("the run still completes", result.status is RunStatus.COMPLETE)
        check(
            "the generator never had the critic's tool",
            generators[0].settings.tools[0].name == "message_parent",
        )

    def check_message_budget(self) -> None:
        check = self.results.check
        sdk = MessagingSdk(critic="Stop: ctx-001 contradicts every candidate.")
        request = _settings_with(_request(items=(_item(),), rounds=3), max_messages=1)
        SuggestionService(sdk).run(request)
        tools = [len(critic.settings.tools) for critic in sdk.critics()]
        check(
            "only the first critic gets the tool under max_messages=1",
            tools == [1, 0, 0],
            str(tools),
        )
        prompts = sdk.generators()[0].prompts
        check(
            "later rounds send full reviews",
            [("# Critic message" in prompt) for prompt in prompts[1:]] == [True, False, False],
        )
        disabled = MessagingSdk(critic="Never sent.")
        SuggestionService(disabled).run(
            _settings_with(_request(items=(_item(),), rounds=2), max_messages=0)
        )
        check(
            "max_messages=0 withholds the tool from every critic",
            all(not critic.settings.tools for critic in disabled.critics()),
        )

    def check_cli_setting(self) -> None:
        check = self.results.check
        check("--max-messages defaults to 2", SuggestionRunInput(goal="Ship").max_messages == 2)
        for value in (-1, 9):
            try:
                SuggestionRunInput(goal="Ship", max_messages=value)
                rejected = False
            except ValueError:
                rejected = True
            check(f"--max-messages rejects {value}", rejected)


def main() -> int:
    results = Results()
    MessageToolSuite(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
