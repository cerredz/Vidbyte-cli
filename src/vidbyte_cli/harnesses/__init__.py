"""Registry of hand-written harnesses.

Adding a harness = drop a folder here and add its instance to HARNESSES. The HarnessRegistry
prefers a match here over a manifest-generated harness; anything not listed is served
dynamically from its backend manifest, so this list is the enrichment set, not the whole
catalog. See the add-harness skill under .claude/skills/ for the full standard.
"""

from __future__ import annotations

from ..lib.harness.module import HarnessModule
from .software_engineering import SoftwareEngineeringHarness

HARNESSES: list[HarnessModule] = [
    SoftwareEngineeringHarness(),
]


def static_harness_map() -> dict[str, HarnessModule]:
    # namespace -> hand-written module, the static source the HarnessRegistry resolves against.
    return {harness.name: harness for harness in HARNESSES}
