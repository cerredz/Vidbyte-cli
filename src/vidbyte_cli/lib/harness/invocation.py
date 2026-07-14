"""The invocation layer: the one place CLI input becomes a backend request.

Every harness command — hand-written or manifest-generated — funnels through here to turn
parsed click params + the command definition (+ an optional repo) into a single
`HarnessRunCreateRequest`. Centralizing it matters because agents call this CLI heavily and
programmatically: the parsing rules (how click's flat, underscored kwargs map back to the
declared args/options) and the *agent-native* error messages (name the exact flag, say what
to pass, exit 2 so a caller can branch on "bad usage") must be identical for every command,
not re-derived per harness.

A harness only writes its own translation when it needs to validate into a richer typed
input first; it then calls back into this layer (see BaseHarness._to_invocation and the
software_engineering harness). This is the "custom dataclasses turn into this request shape"
layer the repo standardizes on (resolves the base.py:48 review comment).
"""

from __future__ import annotations

from ...types.harness import HarnessRepoRef, HarnessRunCreateRequest
from ..errors.cli_error import CliError
from .types import HarnessCommandDef


class InvocationBuilder:
    # Stateless; safe to share as a single instance across every harness.

    def build(
        self,
        harness_name: str,
        command_def: HarnessCommandDef,
        params: dict[str, object],
        repo: HarnessRepoRef | None,
    ) -> HarnessRunCreateRequest:
        # The default translation: split click's flat kwargs back into declared args vs
        # options by name, enforcing required args with an agent-legible error.
        args = {
            arg.name: self._require(params, arg.name, command_def, arg.required)
            for arg in command_def.args
        }
        options = {opt.name: self._pick(params, opt.name) for opt in command_def.options}
        return HarnessRunCreateRequest(
            harness=harness_name,
            command=command_def.name,
            args=args,
            options=options,
            repo=repo,
        )

    def _pick(self, params: dict[str, object], name: str) -> object:
        # click lowercases and underscores param names, so look each spec up by its
        # normalized key ("--dry-run" -> "dry_run").
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
        # Agent-native: name the exact argument and command, and exit 2 (usage error) so a
        # programmatic caller can distinguish "I called it wrong" from a backend failure.
        return CliError(
            f"Missing required argument '{name}' for command '{command_def.name}'. "
            f"Pass it positionally, e.g. `{command_def.name} <{name}>`.",
            exit_code=2,
        )
