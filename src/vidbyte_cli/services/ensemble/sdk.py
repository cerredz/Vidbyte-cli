"""The single lazy binding between this CLI and the Vidbyte SDK's Codex integration.

Every SDK symbol is resolved inside `load()`, never at module scope, because the published
SDK release predates the Codex integration and `vidbyte-cli --help` must keep working in an
environment that does not have it. Callers see only the local Protocol and this class.

Resolution happens before paid admission, so a missing dependency costs nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ...lib.errors.failures import EnsembleSdkUnavailable
from ...types.ensemble import EnsembleInputs

# The SDK module path and the exact symbols this service needs from it.
_CODEX_MODULE = "vidbyte.agents.codex"
_ERRORS_MODULE = "vidbyte.lib.errors"
_REQUIRED = (
    "CodexAgentSettings",
    "CodexForkSettings",
    "CodexHarnessAgentSettings",
    "CodexReasoningEffort",
    "CodexRunInput",
    "CodexSandbox",
    "CodexThreadSettings",
    "CodexTurnSettings",
)


# The two SDK exception classes the service must tell apart: host fault, schema violation.
ErrorTypes = tuple[type[Exception], type[Exception]]


class EnsembleAgent(Protocol):
    """The subset of the SDK agent surface this service actually drives."""

    thread_id: str

    async def arun(self, request: Any) -> Any: ...

    async def afork(self, settings: Any) -> EnsembleAgent: ...


class EnsembleSdk:
    """Holds the resolved SDK symbols and builds every provider value from them."""

    def __init__(self, symbols: dict[str, Any], agent: Any, errors: ErrorTypes) -> None:
        # Storing the resolved symbols is what keeps every SDK name confined to this module.
        self._symbols = symbols
        self._agent_type = agent
        self._error_type, self._schema_error_type = errors

    @classmethod
    def load(cls) -> EnsembleSdk:
        # Imports at call time; an SDK predating the Codex integration fails the same way.
        try:
            codex = __import__(_CODEX_MODULE, fromlist=["*"])
            errors = __import__(_ERRORS_MODULE, fromlist=["*"])
            symbols = {name: getattr(codex, name) for name in _REQUIRED}
            agent_type = codex.CodexHarnessAgent
            resolved = (errors.CodexAgentError, errors.OutputSchemaViolationError)
        except (ImportError, AttributeError) as error:
            raise EnsembleSdkUnavailable(error) from error
        return cls(symbols, agent_type, resolved)

    def agent(self, settings: Any) -> EnsembleAgent:
        # Constructs a root agent; forks are produced by the agent itself, never here.
        created: EnsembleAgent = self._agent_type(settings)
        return created

    def run_input(self, prompt: str) -> Any:
        # One text turn, which is the only input modality this primitive uses.
        return self._symbols["CodexRunInput"].text(prompt)

    def is_provider_error(self, error: Exception) -> bool:
        # Lets the service classify a host failure without importing the SDK's error class.
        return isinstance(error, self._error_type)

    def is_schema_error(self, error: Exception) -> bool:
        # A schema violation is a sibling of CodexAgentError, not a subclass: the host worked,
        # the model just produced output that did not validate. The two need different errors.
        return isinstance(error, self._schema_error_type)

    def root_settings(self, prompt: str, schema: type, codex: Any) -> Any:
        # The planner reads the workspace to design roles, so it is read-only like the roles.
        return self._symbols["CodexHarnessAgentSettings"](
            name="ensemble-planner",
            system_prompt=prompt,
            codex=codex,
            output_schema=schema,
        )

    def fork_settings(self, name: str, prompt: str, schema: type | None, codex: Any) -> Any:
        # A fork inherits everything it does not override; the schema decides its output shape.
        return self._symbols["CodexForkSettings"](
            name=name,
            system_prompt=prompt,
            codex=codex,
            output_schema=schema,
            clear_output_schema=schema is None,
        )

    def codex_settings(self, inputs: EnsembleInputs, cwd: Path, *, write: bool) -> Any:
        # Sandbox is set on thread and turn because an unset value inherits the user's config.
        sandbox = self._sandbox(write=write)
        return self._symbols["CodexAgentSettings"](
            thread=self._symbols["CodexThreadSettings"](
                cwd=str(cwd),
                model=inputs.model or "",
                sandbox=sandbox,
                ephemeral=False,
            ),
            turn=self._symbols["CodexTurnSettings"](
                cwd=str(cwd),
                effort=self._effort(inputs),
                model=inputs.model or "",
                sandbox=sandbox,
            ),
        )

    def _sandbox(self, *, write: bool) -> Any:
        # Read-only is never the provider default, so both modes are named explicitly.
        sandbox = self._symbols["CodexSandbox"]
        return sandbox.WORKSPACE_WRITE if write else sandbox.READ_ONLY

    def _effort(self, inputs: EnsembleInputs) -> Any:
        # An unset effort maps to the provider-default sentinel the SDK strips before sending.
        effort = self._symbols["CodexReasoningEffort"]
        if inputs.reasoning_effort is None:
            return effort.PROVIDER_DEFAULT
        return effort(inputs.reasoning_effort.value)
