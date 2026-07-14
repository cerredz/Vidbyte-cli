"""The per-command definition a harness hands to the runtime.

A command is *data with optional hooks* (composition over deep inheritance): the required
surface is name + description + params, and every varying concern — how CLI input becomes a
backend invocation, how a result is presented — is an optional callable with a sensible
default. A trivial harness overrides nothing; a rich one overrides one or two hooks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from ...types.harness import HarnessRepoRef, HarnessRun, HarnessRunCreateRequest
from ...types.manifest import ArgSpec, OptionSpec

if TYPE_CHECKING:
    from .context import HarnessContext

# Translate parsed CLI input + the current repo (None for harnesses that don't run against
# one) into a backend invocation envelope.
ToInvocation = Callable[[dict[str, object], "HarnessRepoRef | None"], HarnessRunCreateRequest]
# Present a finished run as a terminal string.
Present = Callable[[HarnessRun, "HarnessContext"], str]


@dataclass
class HarnessCommandDef:
    name: str
    description: str
    args: list[ArgSpec] = field(default_factory=list)
    options: list[OptionSpec] = field(default_factory=list)
    # submit = fire and return the queued run; await = poll to completion; read = one GET.
    mode: Literal["submit", "await", "read"] = "submit"
    # Optional hooks — the only harness-specific code most commands need. When None, the
    # BaseHarness defaults apply (pass params straight through / render_status).
    to_invocation: ToInvocation | None = None
    present: Present | None = None
