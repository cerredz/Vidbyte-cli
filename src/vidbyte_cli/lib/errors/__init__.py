"""FILE: src/vidbyte_cli/lib/errors/__init__.py

PURPOSE: Publishes the stable typed-error vocabulary and central boundary handler. Error
construction remains side-effect free; rendering occurs only through an injected manager.

ROLE IN CODEBASE: Commands import CliError and construction helpers from this facade.
CliApplication reaches ErrorHandler through ApplicationContext.

ARCHITECTURE NOTE: Keeping codes, exception data, and exception mapping behind one package
boundary prevents feature slices from coupling to Click or process-exit behavior.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CliError, CliErrorCode, ExitCode: stable failure data and automation vocabulary.
- ErrorHandler: application-boundary exception mapper.
- not_implemented(), usage_error(): common safe constructors.

COMMON MODIFICATION PATTERNS: Export only platform-wide failure contracts, not feature
exceptions or backend provider types.

WHAT NOT TO DO IN THIS FILE:
1. Do not instantiate handlers or output managers.
2. Do not import feature packages.
3. Do not create module-global error state.

KNOWN EDGE CASES: Importing ErrorHandler loads Click and output dependencies, so the package
root does not import this facade during minimal version discovery.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md
documents typed error and exit-code policy.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises this boundary through public CLI failures.
"""

from .cli_error import CliError, not_implemented, usage_error
from .codes import CliErrorCode, ExitCode

__all__ = [
    "CliError",
    "CliErrorCode",
    "ErrorHandler",
    "ExitCode",
    "not_implemented",
    "usage_error",
]


def __getattr__(name: str) -> object:
    # Keep domain/application imports Click-free while preserving the public facade.
    if name == "ErrorHandler":
        from .handler import ErrorHandler

        return ErrorHandler
    raise AttributeError(name)
