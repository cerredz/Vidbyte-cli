"""The last gate a persistence run passes before its first paid turn.

The command buys and verifies the admission; this class re-checks the receipt against the
plan independently, so a caller that skipped verification still cannot start an agent. It
holds no endpoints and never touches the network.
"""

from __future__ import annotations

from ...lib.errors.failures import RuntimeAdmissionNotVerified
from ...lib.runtime_primitives.executor import RuntimeExecutor
from ...types.runtime import PersistenceResult as Result
from ...types.runtime import PersistenceSettings as Tier
from ...types.runtime import RuntimeAdmissionVerdict as Verdict
from ...types.runtime import RuntimeLaunchPlan as Plan
from .session import PersistentCodexSession as Session


class PersistenceRunner:
    """Checks admission at the final boundary before the Codex session can start."""

    def __init__(self, executor: RuntimeExecutor | None = None) -> None:
        # Shares one verdict policy with every other primitive rather than restating it.
        self._executor = executor or RuntimeExecutor()

    def run(self, plan: Plan, settings: Tier, session: Session, verdict: Verdict) -> Result:
        # The session cannot run until the exact requested capability has been admitted.
        self._executor.require_verdict(plan, verdict)
        self._require_persistence_plan(plan)
        return session.run(plan, settings)

    def _require_persistence_plan(self, plan: Plan) -> None:
        # A genuine receipt bought for another product must not open this execution path.
        if plan.capability_id != "runtime.persistence@1" or plan.host.value != "codex":
            raise RuntimeAdmissionNotVerified("persistence_plan_invalid")
