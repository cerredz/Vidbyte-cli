"""Human-readable terminal rendering for harness runs.

The default renderer used by every harness command unless a harness overrides `present`
for a specific command. Only this module and logger.py format terminal output.
"""

from __future__ import annotations

from ...lib.errors.failures import NotImplementedFeature
from ...types.harness import HarnessRun, HarnessSummary


class RunRenderer:
    def render_status(self, run: HarnessRun) -> str:
        # Formats one run's status, latest events, and result into a terminal block.
        raise NotImplementedFeature("run status rendering")

    def render_list(self, runs: list[HarnessRun]) -> str:
        # Formats a list of runs into an aligned summary table.
        raise NotImplementedFeature("run list rendering")

    def render_catalog(self, harnesses: list[HarnessSummary]) -> str:
        # Formats the available-harness catalog into an aligned table.
        raise NotImplementedFeature("harness catalog rendering")
