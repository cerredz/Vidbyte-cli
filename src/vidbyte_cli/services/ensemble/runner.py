"""The ensemble's entry point: resolve the SDK, buy admission once, then run.

Ordering is the whole point of this class. The SDK is resolved before admission is
requested, so an unmet local dependency fails for free; admission is requested before the
planner turn, so no agent ever runs unpaid.
"""

from __future__ import annotations

from ...lib.api.endpoints.runtime import RuntimeEndpoints
from ...types.ensemble import EnsembleInputs, EnsembleResult
from ...types.research import IdempotencyKey
from ...types.runtime import RuntimeAdmissionGrant, RuntimeAdmissionRequest, RuntimeLaunchPlan
from .sdk import EnsembleSdk
from .service import EnsembleService
from .settings import EnsembleStages


class EnsembleRunner:
    """Sequences dependency resolution, paid admission, and the ensemble algorithm."""

    def __init__(self, endpoints: RuntimeEndpoints) -> None:
        # Admission is the only network call in the whole primitive; execution stays local.
        self._endpoints = endpoints

    def run(self, plan: RuntimeLaunchPlan, inputs: EnsembleInputs) -> EnsembleResult:
        # Resolve the SDK first: a missing Codex integration must never cost the caller money.
        sdk = EnsembleSdk.load()
        grant = self._admit(plan)
        stages = EnsembleStages(sdk, inputs, plan.working_directory)
        return EnsembleService(stages).run(grant.charged_cents)

    def _admit(self, plan: RuntimeLaunchPlan) -> RuntimeAdmissionGrant:
        # One replay-safe purchase per invocation, so a retried request is not charged twice.
        request = RuntimeAdmissionRequest(host=plan.host)
        return self._endpoints.admit_same_host_ensemble(request, str(IdempotencyKey.create(None)))
