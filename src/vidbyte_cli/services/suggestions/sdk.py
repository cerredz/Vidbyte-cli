"""Lazy binding between the suggestion service and the Vidbyte SDK.

All SDK symbols resolve inside `load()`, never at module scope, so `--help`
and `categories` keep working where the SDK predates the integration. The CLI
maps its provider names to SDK identifiers explicitly instead of assuming
they already match.
"""

from __future__ import annotations

from typing import Any, Protocol

from ...lib.errors.failures import SuggestionSdkUnavailable

_CODEX_MODULE = "vidbyte.agents.codex"
_ERRORS_MODULE = "vidbyte.lib.errors"
_REQUIRED = (
    "CodexAgentSettings",
    "CodexForkSettings",
    "CodexHarnessAgentSettings",
    "CodexRunInput",
    "CodexThreadSettings",
)


class SuggestionAgent(Protocol):
    """Subset of the SDK agent surface the suggestion workflow drives."""

    thread_id: str

    async def arun(self, request: Any) -> Any: ...

    async def afork(self, settings: Any) -> SuggestionAgent: ...


class SuggestionSdk:
    """Holds resolved SDK symbols and builds generator/critic settings."""

    def __init__(
        self, symbols: dict[str, Any], agent: Any, errors: tuple[type[Exception], type[Exception]]
    ) -> None:
        # Stores resolved symbols so no SDK name leaks outside this module.
        self._symbols = symbols
        self._agent_type = agent
        self._error_type, self._schema_error_type = errors

    @classmethod
    def load(cls) -> SuggestionSdk:
        # Imports at call time; a predating SDK fails with a typed error.
        try:
            codex = __import__(_CODEX_MODULE, fromlist=["*"])
            errors = __import__(_ERRORS_MODULE, fromlist=["*"])
            symbols = {name: getattr(codex, name) for name in _REQUIRED}
            agent_type = codex.CodexHarnessAgent
            resolved = (errors.CodexAgentError, errors.OutputSchemaViolationError)
        except (ImportError, AttributeError) as error:
            raise SuggestionSdkUnavailable(error) from error
        return cls(symbols, agent_type, resolved)

    def agent(self, settings: Any) -> SuggestionAgent:
        # Constructs a root agent; critic/generator forks come from the agent.
        created: SuggestionAgent = self._agent_type(settings)
        return created

    def run_input(self, prompt: str) -> Any:
        # Single text turn, the only input modality this workflow uses.
        return self._symbols["CodexRunInput"].text(prompt)

    def is_provider_error(self, error: Exception) -> bool:
        # Classifies host faults without importing SDK error types elsewhere.
        return isinstance(error, self._error_type)

    def is_schema_error(self, error: Exception) -> bool:
        # Schema violations are siblings of host errors and need their own path.
        return isinstance(error, self._schema_error_type)

    def generator_settings(
        self, system_prompt: str, schema: type | None, provider: str | None, model: str | None
    ) -> Any:
        # Generator runs with no execution tools; provider/model ride through.
        return self._symbols["CodexHarnessAgentSettings"](
            name="suggestion-generator", system_prompt=system_prompt, output_schema=schema
        )

    def critic_settings(self, system_prompt: str, schema: type | None) -> Any:
        # Critic is a separate agent with its own history, never a fork of turns.
        return self._symbols["CodexHarnessAgentSettings"](
            name="suggestion-critic", system_prompt=system_prompt, output_schema=schema
        )
