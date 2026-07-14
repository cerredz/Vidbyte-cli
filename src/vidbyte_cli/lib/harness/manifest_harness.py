"""A harness whose commands come from a backend manifest instead of hand-written code.

This is the unification point: ManifestHarness satisfies the same contract as any
hand-written BaseHarness, so a brand-new backend harness needs *zero* code in this repo —
the registry wraps its manifest in a ManifestHarness and the generic dispatch/present/error
lifecycle applies unchanged. Hand-written harnesses in src/harnesses/ exist only to enrich
UX beyond what a manifest can express.
"""

from __future__ import annotations

from ...types.manifest import HarnessCommandSpec, HarnessManifest
from .base import BaseHarness
from .context import HarnessContext
from .types import HarnessCommandDef


class ManifestHarness(BaseHarness):
    def __init__(self, manifest: HarnessManifest) -> None:
        self._manifest = manifest
        self.name = manifest.name
        self.description = manifest.description

    def commands(self, ctx: HarnessContext) -> list[HarnessCommandDef]:
        # Maps each manifest command spec to a command def using the default translation and
        # presentation (no per-command hooks). Rich UX is opt-in via a hand-written harness.
        return [self._to_command_def(spec) for spec in self._manifest.commands]

    def _to_command_def(self, spec: HarnessCommandSpec) -> HarnessCommandDef:
        # All logic stays on the class (resolves the manifest_harness.py:37 review comment).
        return HarnessCommandDef(
            name=spec.name,
            description=spec.description,
            args=spec.args,
            options=spec.options,
            mode=spec.mode,
        )
