"""Lazily binds the suggestion service to Vidbyte SDK Codex agents.

This is the only module that imports SDK symbols. It constructs read-only,
structured-output agents and places one validated stage context primitive in
each fresh context manager.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast

from ...lib.errors.failures import SuggestionSdkUnavailable
from ...lib.io.codex_attachments import CodexAttachmentInputBuilder
from ...types.attachments import AttachmentBundle
from ...types.suggestions import SuggestionAgentContext, SuggestionCriticContextPrimitive

_CODEX_MODULE = "vidbyte.agents.codex"
_CONTEXT_MODULE = "vidbyte.context"
_ERRORS_MODULE = "vidbyte.lib.errors"
_REQUIRED = (
    "CodexAgentSettings",
    "CodexApprovalMode",
    "CodexHarnessAgentSettings",
    "CodexRunInput",
    "CodexSandbox",
    "CodexThreadSettings",
    "CodexTurnSettings",
)
_PROVIDER_MAP = {"openai": "openai"}


@dataclass(frozen=True, slots=True)
class SuggestionSdkBindings:
    """Validated SDK classes and errors resolved together by the lazy loader."""

    symbols: Mapping[str, Any]
    agent_type: type
    provider_error_type: type[Exception]
    schema_error_type: type[Exception]

    def __post_init__(self) -> None:
        expected = frozenset((*_REQUIRED, "ContextManager", "ContextWindowPlacement"))
        if frozenset(self.symbols) != expected:
            raise ValueError("Suggestion SDK bindings do not match the required surface.")
        if any(not callable(symbol) for symbol in self.symbols.values()):
            raise TypeError("Every suggestion SDK binding must be callable.")
        if not isinstance(self.agent_type, type):
            raise TypeError("Suggestion SDK agent_type must be a class.")
        for field_name in ("provider_error_type", "schema_error_type"):
            value = getattr(self, field_name)
            if not isinstance(value, type) or not issubclass(value, Exception):
                raise TypeError(f"Suggestion SDK {field_name} must be an Exception class.")
        object.__setattr__(self, "symbols", MappingProxyType(dict(self.symbols)))


@dataclass(frozen=True, slots=True)
class SuggestionAgentSettingsInput:
    """Strict local input for one generator or critic Codex configuration."""

    role: Literal["generator", "critic"]
    system_prompt: str
    context: SuggestionAgentContext
    output_schema: type | Mapping[str, Any]
    provider: str | None = None
    model: str | None = None
    tools: tuple[Callable[..., Any], ...] = ()

    def __post_init__(self) -> None:
        if self.role not in ("generator", "critic"):
            raise ValueError("Suggestion agent role must be generator or critic.")
        if type(self.system_prompt) is not str or not self.system_prompt.strip():
            raise ValueError("Suggestion agent system_prompt must be non-empty.")
        if not isinstance(self.context, SuggestionAgentContext):
            raise TypeError("Suggestion agent context must be SuggestionAgentContext.")
        if not isinstance(self.output_schema, (type, Mapping)):
            raise TypeError("Suggestion agent output_schema must be a class or mapping.")
        if not isinstance(self.tools, tuple) or any(not callable(tool) for tool in self.tools):
            raise TypeError("Suggestion agent tools must be a tuple of callables.")
        for name, value in (("provider", self.provider), ("model", self.model)):
            if value is not None and (type(value) is not str or not value.strip()):
                raise ValueError(f"Suggestion agent {name} must be None or non-empty.")


@dataclass(frozen=True, slots=True)
class SuggestionTextInput:
    """Strict local input for the single text turn used by this workflow."""

    prompt: str
    attachments: AttachmentBundle = field(default_factory=AttachmentBundle)

    def __post_init__(self) -> None:
        if type(self.prompt) is not str or not self.prompt.strip():
            raise ValueError("Suggestion text prompt must be non-empty.")


class SuggestionAgent(Protocol):
    """Subset of CodexHarnessAgent driven by the suggestion workflow."""

    thread_id: str

    async def arun(self, request: Any) -> Any: ...


@dataclass(slots=True)
class SuggestionAgentSession:
    """One persistent generator agent and its replaceable context window."""

    agent: SuggestionAgent
    context_manager: Any
    thread_id: str = ""

    def verify_thread(self) -> None:
        # Pins the first real SDK thread identity and rejects silent conversation replacement.
        current = str(self.agent.thread_id).strip()
        if not current:
            raise ValueError("Suggestion generator returned an empty thread id.")
        if self.thread_id and current != self.thread_id:
            raise ValueError("Suggestion generator thread changed during refinement.")
        self.thread_id = current


class SuggestionSdk:
    """Translates strict local values into fresh, read-only Codex agents."""

    def __init__(self, bindings: SuggestionSdkBindings) -> None:
        self._bindings = bindings

    @classmethod
    def load(cls) -> SuggestionSdk:
        """Resolve the pinned SDK only when a model-backed operation needs it."""
        try:
            codex = __import__(_CODEX_MODULE, fromlist=["*"])
            context = __import__(
                _CONTEXT_MODULE, fromlist=["ContextManager", "ContextWindowPlacement"]
            )
            errors = __import__(_ERRORS_MODULE, fromlist=["*"])
            symbols = {name: getattr(codex, name) for name in _REQUIRED}
            symbols["ContextManager"] = context.ContextManager
            symbols["ContextWindowPlacement"] = context.ContextWindowPlacement
            bindings = SuggestionSdkBindings(
                symbols=symbols,
                agent_type=codex.CodexHarnessAgent,
                provider_error_type=errors.CodexAgentError,
                schema_error_type=errors.OutputSchemaViolationError,
            )
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            raise SuggestionSdkUnavailable(error) from error
        return cls(bindings)

    def agent(self, settings: Any) -> SuggestionAgent:
        """Construct one new SDK agent from already validated settings."""
        return cast(SuggestionAgent, self._bindings.agent_type(settings))

    def agent_session(self, request: SuggestionAgentSettingsInput) -> SuggestionAgentSession:
        # Keeps the generator agent and context manager together across refinement turns.
        settings = self.agent_settings(request)
        return SuggestionAgentSession(self.agent(settings), settings.context_manager)

    def place_critic_context(
        self, session: SuggestionAgentSession, context: SuggestionCriticContextPrimitive
    ) -> None:
        # Replaces the latest critic block at the end of the persistent generator conversation.
        if not isinstance(session, SuggestionAgentSession):
            raise TypeError("place_critic_context requires SuggestionAgentSession.")
        if not isinstance(context, SuggestionCriticContextPrimitive):
            raise TypeError("place_critic_context requires SuggestionCriticContextPrimitive.")
        placement = self._bindings.symbols["ContextWindowPlacement"].END_OF_CONVERSATION
        session.context_manager.upsert(context, placement=placement)

    def replace_stage_context(
        self, session: SuggestionAgentSession, context: SuggestionAgentContext
    ) -> None:
        # Removes an initial candidate seed after it has entered the generator's own history.
        if not isinstance(session, SuggestionAgentSession):
            raise TypeError("replace_stage_context requires SuggestionAgentSession.")
        if not isinstance(context, SuggestionAgentContext):
            raise TypeError("replace_stage_context requires SuggestionAgentContext.")
        session.context_manager.remove_by_id("suggestion-context:stage")
        session.context_manager.place_after_system_prompt(context)

    def run_input(self, request: SuggestionTextInput) -> Any:
        """Translate one local text request into the SDK's typed input."""
        if not isinstance(request, SuggestionTextInput):
            raise TypeError("run_input requires SuggestionTextInput.")
        return CodexAttachmentInputBuilder().build(request.prompt, request.attachments)

    def is_provider_error(self, error: Exception) -> bool:
        """Identify SDK transport/host failures without importing SDK types elsewhere."""
        return isinstance(error, self._bindings.provider_error_type)

    def is_schema_error(self, error: Exception) -> bool:
        """Identify a provider reply that violated the declared output schema."""
        return isinstance(error, self._bindings.schema_error_type)

    def agent_settings(self, request: SuggestionAgentSettingsInput) -> Any:
        """Build the exact read-only SDK settings for one independent context window."""
        if not isinstance(request, SuggestionAgentSettingsInput):
            raise TypeError("agent_settings requires SuggestionAgentSettingsInput.")
        symbols = self._bindings.symbols
        provider = "" if request.provider is None else _PROVIDER_MAP.get(request.provider)
        if request.provider is not None and provider is None:
            raise ValueError(f"Unsupported suggestion provider: {request.provider}")
        sandbox = symbols["CodexSandbox"].READ_ONLY
        deny = symbols["CodexApprovalMode"].DENY_ALL
        codex = symbols["CodexAgentSettings"](
            thread=symbols["CodexThreadSettings"](
                model=request.model or "",
                model_provider=provider or "",
                sandbox=sandbox,
                approval_mode=deny,
            ),
            turn=symbols["CodexTurnSettings"](
                model=request.model or "",
                sandbox=sandbox,
                approval_mode=deny,
            ),
        )
        manager = symbols["ContextManager"]()
        manager.place_after_system_prompt(request.context)
        values: dict[str, Any] = {
            "name": f"suggestion-{request.role}",
            "system_prompt": request.system_prompt,
            "codex": codex,
            "context_manager": manager,
            "output_schema": request.output_schema,
        }
        if request.tools:
            values["tools"] = request.tools
        return symbols["CodexHarnessAgentSettings"](
            **values,
        )


__all__ = [
    "SuggestionAgent",
    "SuggestionAgentSession",
    "SuggestionAgentSettingsInput",
    "SuggestionSdk",
    "SuggestionSdkBindings",
    "SuggestionTextInput",
]
