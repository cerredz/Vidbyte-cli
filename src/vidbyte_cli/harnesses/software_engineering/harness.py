"""SoftwareEngineeringHarness — the first hand-written harness, shown end to end.

This is the reference implementation for the repo's harness standard (see the add-harness
skill under .claude/skills/). Integrating a harness is four steps: (1) types.py for its data,
(2) commands.py to declare the surface, (3) this class binding name + description + commands
+ whether it needs a repo, (4) register the instance in vidbyte_cli.harnesses. Nothing in
commands/, cli.py, or the click wiring changes.
"""

from __future__ import annotations

from ...lib.harness.base import BaseHarness
from ...lib.harness.context import HarnessContext
from ...lib.harness.types import HarnessCommandDef
from .commands import build_commands


class SoftwareEngineeringHarness(BaseHarness):
    name = "software-engineering"
    description = "Implement changes and open pull requests on your repo"
    # This harness runs against the caller's checkout, so dispatch attaches the repo ref.
    requires_repo = True

    def commands(self, ctx: HarnessContext) -> list[HarnessCommandDef]:
        return build_commands()
