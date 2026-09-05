"""One run's shared collaborators, and the sandbox policy for each of its three stages.

This is where "exactly one agent may write" is decided, so the invariant is checkable by
reading a single file: `root` and `proposal` are read-only, `implementer` is not. It also
carries the run's sdk, prompts, and inputs so the service does not thread them everywhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...types.ensemble import EnsembleInputs, GeneratedRole, RolePlan, RoleProposal
from .prompts import EnsemblePrompts
from .sdk import EnsembleSdk


class EnsembleStages:
    """Holds one run's collaborators and builds the settings each stage needs."""

    def __init__(self, sdk: EnsembleSdk, inputs: EnsembleInputs, cwd: Path) -> None:
        # One instance per run, so working directory and caller options cannot drift by stage.
        self.sdk = sdk
        self.inputs = inputs
        self.prompts = EnsemblePrompts()
        self._cwd = cwd

    def root(self) -> Any:
        # Stage one designs the roster and only reads, so it gets no write access either.
        prompt = self.prompts.planner_system_prompt(self.inputs.roles)
        return self.sdk.root_settings(prompt, RolePlan, self._codex(write=False))

    def proposal(self, role: GeneratedRole) -> Any:
        # Stage two: read-only, and its structured output is what makes it a proposal.
        prompt = self.prompts.role_system_prompt(role)
        return self.sdk.fork_settings(role.name, prompt, RoleProposal, self._codex(write=False))

    def implementer(self) -> Any:
        # Stage three is the only bundle in this file that enables workspace writes.
        prompt = self.prompts.implementer_system_prompt()
        return self.sdk.fork_settings("implementer", prompt, None, self._codex(write=True))

    def _codex(self, *, write: bool) -> Any:
        # Provider settings are built by the sdk module; only the write axis is decided here.
        return self.sdk.codex_settings(self.inputs, self._cwd, write=write)
