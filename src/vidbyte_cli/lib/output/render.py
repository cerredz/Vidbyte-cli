"""FILE: src/vidbyte_cli/lib/output/render.py

PURPOSE: Defines the existing generic harness human-rendering seam for run, list, and
catalog results. It returns strings only; output format selection and stream writes belong
to OutputManager.

ROLE IN CODEBASE: HarnessContext supplies RunRenderer to BaseHarness when a command has no
custom presenter. Generic harness transport work implements these methods in PR 4.

ARCHITECTURE NOTE: Pure human rendering stays separate from versioned machine documents so
prose can improve without breaking automation schemas.

FUNCTION INVENTORY (reviewed 2026-07-26):
- RunRenderer.render_status(run) -> str: human summary for one run.
- RunRenderer.render_list(runs) -> str: human summary for run collection.
- RunRenderer.render_catalog(harnesses) -> str: human summary for harness catalog.

COMMON MODIFICATION PATTERNS: Keep methods pure, accept typed models, and pair implemented
human output with a machine presenter at the command/application boundary.

WHAT NOT TO DO IN THIS FILE:
1. Do not call print, sys streams, or OutputManager.
2. Do not serialize JSON or choose an output format.
3. Do not perform network, credential, config, or filesystem work.
4. Do not add research-specific artifact/source rendering.

KNOWN EDGE CASES: Empty collections and partial run data need useful text once implemented.
Current methods remain explicit typed stubs until the generic API platform PR.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md
documents the separation between presenters and output policy.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py verifies the generic harness command tree remains importable.
"""

from __future__ import annotations

from ...lib.errors.cli_error import not_implemented
from ...types.harness import HarnessRun, HarnessSummary


class RunRenderer:
    """Pure human presenter for generic harness models."""

    def render_status(self, run: HarnessRun) -> str:
        # Formats one run's status, latest events, and result into a terminal block.
        raise not_implemented("run status rendering")

    def render_list(self, runs: list[HarnessRun]) -> str:
        # Formats a list of runs into an aligned summary table.
        raise not_implemented("run list rendering")

    def render_catalog(self, harnesses: list[HarnessSummary]) -> str:
        # Formats the available-harness catalog into an aligned table.
        raise not_implemented("harness catalog rendering")
