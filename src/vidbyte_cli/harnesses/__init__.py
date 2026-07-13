"""Registry of hand-written harnesses.

Adding a harness = drop a folder here and add its instance to HARNESSES. The factory
prefers a match here over a manifest-generated harness; anything not listed is served
dynamically from its backend manifest, so this list is the enrichment set, not the whole
catalog.
"""

from __future__ import annotations

from ..lib.harness.module import HarnessModule
from .job_applier import JobApplierHarness

HARNESSES: list[HarnessModule] = [
    JobApplierHarness(),
]


def find_static_harness(name: str) -> HarnessModule | None:
    # Returns the hand-written harness for a namespace, or None to fall back to a manifest.
    for harness in HARNESSES:
        if harness.name == name:
            return harness
    return None
