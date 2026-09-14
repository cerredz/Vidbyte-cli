"""Strict, lazy binding between the suggestion service and the Vidbyte SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol

from ...lib.errors.failures import SuggestionSdkUnavailable
from ...types.suggestions import SuggestionContextPrimitive

_CODEX_MODULE = "vidbyte.agents.codex"
_CONTEXT_MODULE = "vidbyte.context"
_ERRORS_MODULE = "vidbyte.lib.errors"
_REQUIRED = (
    "CodexAgentSettings",
    "CodexForkSettings",
    "CodexHarnessAgentSettings",
    "CodexRunInput",
    "CodexThreadSettings",
)
_BINDING_NAMES = frozenset((*_REQUIRED, "ContextManager"))


def _optional_text(owner: str, field_name: str, value: str | None) -> None:
    if value is not None and (type(value) is not str or not value.strip()):
        raise ValueError(f"{owner} {field_name} must be None or a non-empty string.")


@dataclass(frozen=True, slots=True)
class SuggestionSdkBindings:
    """Validated SDK classes and errors resolved together by the lazy loader."""

    symbols: Mapping[str, Any]
    agent_type: type
    provider_error_type: type[Exception]
    schema_error_type: type[Exception]

    def __post_init__(self) -> None:
        if not isinstance(self.symbols, Mapping) or set(self.symbols) != _BINDING_NAMES:
            raise ValueError(
                "Suggestion SDK symbols must contain exactly the required Codex and context "
                "bindings."
            )
        if any(not callable(symbol) for symbol in self.symbols.values()):
            raise TypeError("Every suggestion SDK symbol must be callable.")
        if not isinstance(self.agent_type, type):
            raise TypeError("Suggestion SDK agent_type must be a class.")
        for field_name in ("provider_error_type", "schema_error_type"):
            error_type = getattr(self, field_name)
            if not isinstance(error_type, type) or not issubclass(error_type, Exception):
                raise TypeError(f"Suggestion SDK {field_name} must be an Exception class.")
        object.__setattr__(self, "symbols", MappingProxyType(dict(self.symbols)))


@dataclass(frozen=True, slots=True)
class SuggestionAgentSettingsInput:
    """Strict local input used to construct one SDK generator or critic configuration."""

    role: Literal["generator", "critic"]
    system_prompt: str
    context: SuggestionContextPrimitive
    output_schema: type | Mapping[str, Any] | None = None
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ("generator", "critic"):
            raise ValueError("Suggestion agent role must be 'generator' or 'critic'.")
        if type(self.system_prompt) is not str or not self.system_prompt.strip():
            raise ValueError("Suggestion agent system_prompt must be a non-empty string.")
        if not isinstance(self.context, SuggestionContextPrimitive):
            raise TypeError("Suggestion agent context must be SuggestionContextPrimitive.")
        if self.output_schema is not None and not isinstance(self.output_schema, (type, Mapping)):
            raise TypeError("Suggestion agent output_schema must be a class, mapping, or None.")
        _optional_text("Suggestion agent", "provider", self.provider)
        _optional_text("Suggestion agent", "model", self.model)


@dataclass(frozen=True, slots=True)
class SuggestionTextInput:
    """Strict local input for the single text-turn modality used by this workflow."""

    prompt: str

    def __post_init__(self) -> None:
        if type(self.prompt) is not str or not self.prompt.strip():
            raise ValueError("Suggestion text prompt must be a non-empty string.")


class SuggestionAgent(Protocol):
    """Subset of the SDK agent surface the suggestion workflow drives."""

    thread_id: str

    async def arun(self, request: Any) -> Any: ...

    async def afork(self, settings: Any) -> SuggestionAgent: ...


class SuggestionSdk:
    """Hold validated SDK bindings and translate strict local inputs at one boundary."""

    def __init__(self, bindings: SuggestionSdkBindings) -> None:
        if not isinstance(bindings, SuggestionSdkBindings):
            raise TypeError("SuggestionSdk requires validated SuggestionSdkBindings.")
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
        """Construct a root SDK agent from already translated SDK settings."""
        created: SuggestionAgent = self._bindings.agent_type(settings)
        return created

    def run_input(self, request: SuggestionTextInput) -> Any:
        """Translate one validated local text request into the SDK input type."""
        if not isinstance(request, SuggestionTextInput):
            raise TypeError("run_input requires SuggestionTextInput.")
        return self._bindings.symbols["CodexRunInput"].text(request.prompt)

    def is_provider_error(self, error: Exception) -> bool:
        return isinstance(error, self._bindings.provider_error_type)

    def is_schema_error(self, error: Exception) -> bool:
        return isinstance(error, self._bindings.schema_error_type)

    def agent_settings(self, request: SuggestionAgentSettingsInput) -> Any:
        """Translate one validated local settings object into pinned SDK dataclasses."""
        if not isinstance(request, SuggestionAgentSettingsInput):
            raise TypeError("agent_settings requires SuggestionAgentSettingsInput.")
        thread = self._bindings.symbols["CodexThreadSettings"](
            model=request.model or "",
            model_provider=request.provider or "",
        )
        codex = self._bindings.symbols["CodexAgentSettings"](thread=thread)
        return self._bindings.symbols["CodexHarnessAgentSettings"](
            name=f"suggestion-{request.role}",
            system_prompt=request.system_prompt,
            codex=codex,
            context_manager=self._context_manager(request.context),
            output_schema=request.output_schema,
        )

    def _context_manager(self, context: SuggestionContextPrimitive) -> Any:
        manager = self._bindings.symbols["ContextManager"]()
        manager.place_after_system_prompt(context)
        return manager
