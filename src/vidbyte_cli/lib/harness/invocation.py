"""FILE: src/vidbyte_cli/lib/harness/invocation.py

PURPOSE: Converts parsed generic harness arguments and options into the one backend request
shape shared by static and manifest-backed harnesses. It also owns consistent missing-input
classification.

ROLE IN CODEBASE: BaseHarness delegates default request translation here. HarnessCommandDef
supplies declarative input names and HarnessRunCreateRequest is the wire-facing result.

ARCHITECTURE NOTE: Central translation prevents dynamic and hand-written harnesses from
drifting in Click name normalization or agent-readable usage failures.

FUNCTION INVENTORY (reviewed 2026-07-26):
- InvocationBuilder.build(...) -> HarnessRunCreateRequest: translates one command call.
- InvocationBuilder._pick(params, name) -> object: resolves Click-normalized names.
- InvocationBuilder._require(...) -> object: validates a declared required argument.

COMMON MODIFICATION PATTERNS: Add only translation rules common to every generic harness;
use a command's explicit hook for richer feature input.

WHAT NOT TO DO IN THIS FILE:
1. Do not perform HTTP requests, credential reads, repository inspection, or output.
2. Do not add research-specific request fields.
3. Do not return unclassified ValueError for invalid user input.
4. Do not infer undeclared options.

KNOWN EDGE CASES: Click changes dashes to underscores, optional values may be None, and
required positional inputs must return exit 2 with an actionable hint.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md
documents generic harness request translation.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises representative generic harness command registration.
"""

from __future__ import annotations

from ...types.harness import HarnessRepoRef, HarnessRunCreateRequest
from ..errors.cli_error import CliError, usage_error
from .types import HarnessCommandDef


class InvocationBuilder:
    """Default translation from flat Click values to a harness request."""

    def build(
        self,
        harness_name: str,
        command_def: HarnessCommandDef,
        params: dict[str, object],
        repo: HarnessRepoRef | None,
    ) -> HarnessRunCreateRequest:
        # Split Click's flat kwargs back into declared arguments and options.
        args = {
            argument.name: self._require(
                params,
                argument.name,
                command_def,
                argument.required,
            )
            for argument in command_def.args
        }
        options = {option.name: self._pick(params, option.name) for option in command_def.options}
        return HarnessRunCreateRequest(
            harness=harness_name,
            command=command_def.name,
            args=args,
            options=options,
            repo=repo,
        )

    def _pick(self, params: dict[str, object], name: str) -> object:
        # Click lowercases and underscores names, so normalize the declared spelling.
        return params.get(name.replace("-", "_"))

    def _require(
        self,
        params: dict[str, object],
        name: str,
        command_def: HarnessCommandDef,
        required: bool,
    ) -> object:
        value = self._pick(params, name)
        if required and value is None:
            raise self._missing_argument(command_def, name)
        return value

    def _missing_argument(self, command_def: HarnessCommandDef, name: str) -> CliError:
        # Exit 2 lets an agent distinguish its invocation mistake from an operational failure.
        return usage_error(
            f"Missing required argument '{name}' for command '{command_def.name}'. "
            f"Pass it positionally, e.g. `{command_def.name} <{name}>`.",
        )
