"""JobApplierHarness — a hand-written harness, shown end to end.

Integrating a harness is four steps: (1) types.py for its data, (2) commands.py to declare
the surface, (3) this class binding name + description + commands, (4) register the instance
in vidbyte_cli.harnesses. Nothing in commands/, cli.py, or click wiring changes.
"""

from __future__ import annotations

from ...lib.harness.base import BaseHarness
from ...lib.harness.context import HarnessContext
from ...lib.harness.types import HarnessCommandDef
from .commands import build_commands


class JobApplierHarness(BaseHarness):
    name = "job-applier"
    description = "Apply to jobs from your resume"

    def commands(self, ctx: HarnessContext) -> list[HarnessCommandDef]:
        return build_commands()
