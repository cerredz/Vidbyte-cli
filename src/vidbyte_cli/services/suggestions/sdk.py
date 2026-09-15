"""Lazily binds the suggestion service to Vidbyte SDK Codex agents.

This is the only module that imports SDK symbols. It constructs read-only,
structured-output agents and places one validated custom context primitive in
each fresh context manager.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast

from ...lib.errors.failures import SuggestionSdkUnavailable
from ...lib.io.codex_attachments import CodexAttachmentInputBuilder
from ...types.attachments import AttachmentBundle
from ...types.suggestions import SuggestionContextPrimitive

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
        expected = frozenset((*_REQUIRED, "ContextManager"))
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
    context: SuggestionContextPrimitive
    output_schema: type | Mapping[str, Any]
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ("generator", "critic"):
            raise ValueError("Suggestion agent role must be generator or critic.")
        if type(self.system_prompt) is not str or not self.system_prompt.strip():
            raise ValueError("Suggestion agent system_prompt must be non-empty.")
        if not isinstance(self.context, SuggestionContextPrimitive):
            raise TypeError("Suggestion agent context must be SuggestionContextPrimitive.")
        if not isinstance(self.output_schema, (type, Mapping)):
            raise TypeError("Suggestion agent output_schema must be a class or mapping.")
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


class SuggestionSdk:
    """Translates strict local values into fresh, read-only Codex agents."""

    def __init__(self, bindings: SuggestionSdkBindings) -> None:
        self._bindings = bindings

    @classmethod
    def load(cls) -> SuggestionSdk:
        """Resolve the pinned SDK only when a model-backed operation needs it."""
        try:
            codex = __import__(_CODEX_MODULE, fromlist=["*"])
            context = __import__(_CONTEXT_MODULE, fromlist=["ContextManager"])
            errors = __import__(_ERRORS_MODULE, fromlist=["*"])
            symbols = {name: getattr(codex, name) for name in _REQUIRED}
            symbols["ContextManager"] = context.ContextManager
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
        return symbols["CodexHarnessAgentSettings"](
            name=f"suggestion-{request.role}",
            system_prompt=request.system_prompt,
            codex=codex,
            context_manager=manager,
            output_schema=request.output_schema,
        )


__all__ = [
    "SuggestionAgent",
    "SuggestionAgentSettingsInput",
    "SuggestionSdk",
    "SuggestionSdkBindings",
    "SuggestionTextInput",
]
