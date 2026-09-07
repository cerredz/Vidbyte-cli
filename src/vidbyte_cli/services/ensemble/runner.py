"""Launches one verified ensemble run: build the stages, then run the algorithm.

The command admits and verifies before calling here, so this class never touches the
network: it receives the loaded SDK and the verified grant, builds the run's stages, and
hands them to the service. The charged admission travels with the grant into the result.
"""

from __future__ import annotations

from ...types.ensemble import EnsembleInputs, EnsembleResult
from ...types.runtime import RuntimeAdmissionGrant, RuntimeLaunchPlan
from .sdk import EnsembleSdk
from .service import EnsembleService
from .settings import EnsembleStages


class EnsembleRunner:
    """Builds one run's stages from verified inputs and runs the ensemble algorithm."""

    def run(
        self,
        plan: RuntimeLaunchPlan,
        inputs: EnsembleInputs,
        sdk: EnsembleSdk,
        grant: RuntimeAdmissionGrant,
    ) -> EnsembleResult:
        # No admission here: the command already bought and verified it, so starting the
        # service is the only thing left that can fail.
        stages = EnsembleStages(sdk, inputs, plan.working_directory)
        return EnsembleService(stages).run(grant.charged_cents)
