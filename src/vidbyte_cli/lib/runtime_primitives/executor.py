"""Execution boundary for admitted local runtime primitives, and the one verdict policy.

Adversarial-team retains its explicit scaffold; every process-launching path requires a
matching deterministic admission verdict, which `require_verdict` is the single source of.
`persistence` and `same-host-ensemble` are deliberately absent: they run in
`services/persistence/` and `services/ensemble/`, because a service may depend on `lib/`
while nothing in `lib/` may depend on a service.
"""

from __future__ import annotations

from typing import NoReturn

from ...types.runtime import RuntimeAdmissionVerdict as Verdict
from ...types.runtime import RuntimeLaunchPlan as Plan
from ..errors.failures import RuntimeAdmissionNotVerified, RuntimeExecutionNotImplemented


class RuntimeExecutor:
    """Checks admission at the final boundary before an agent can start."""

    def execute_adversarial_team(self, plan: Plan, verdict: Verdict | None = None) -> NoReturn:
        # Keeps the existing primitive inert after validating its admission.
        self.require_verdict(plan, verdict)
        raise RuntimeExecutionNotImplemented()

    def require_verdict(self, plan: Plan, verdict: Verdict | None) -> None:
        # Rejects absent, false, mismatched or empty receipts independently of command checks.
        if verdict is None or not verdict.admitted:
            raise RuntimeAdmissionNotVerified()
        if verdict.capability_id != plan.capability_id or not verdict.admission_id.strip():
            raise RuntimeAdmissionNotVerified()
