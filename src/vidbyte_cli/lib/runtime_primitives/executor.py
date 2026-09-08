"""Execution boundary for admitted local runtime primitives.

Persistence and task-board have implementations; adversarial-team retains its scaffold.
Every process-launching path requires a matching deterministic admission verdict.
`same-host-ensemble` is deliberately absent: it runs in `services/ensemble/`, because a
service may depend on `lib/` while nothing in `lib/` may depend on a service.
"""

from __future__ import annotations

from typing import NoReturn

from ...types.runtime import PersistenceResult as Result
from ...types.runtime import PersistenceSettings as Tier
from ...types.runtime import RuntimeAdmissionVerdict as Verdict
from ...types.runtime import RuntimeLaunchPlan as Plan
from ...types.runtime import TaskBoardResult as BoardResult
from ...types.runtime import TaskBoardSettings as BoardSettings
from ..errors.failures import RuntimeAdmissionNotVerified, RuntimeExecutionNotImplemented
from .persistence import PersistentCodexSession as Session
from .task_board import TaskBoardCodexSession as BoardSession


class RuntimeExecutor:
    """Checks admission at the final boundary before an agent can start."""

    def execute_adversarial_team(self, plan: Plan, verdict: Verdict | None = None) -> NoReturn:
        # Keeps the existing primitive inert after validating its admission.
        self._require_verdict(plan, verdict)
        raise RuntimeExecutionNotImplemented()

    def execute_persistence(self, plan: Plan, tune: Tier, host: Session, proof: Verdict) -> Result:
        # The session cannot run until the exact requested capability has been admitted.
        self._require_verdict(plan, proof)
        if plan.capability_id != "runtime.persistence@1" or plan.host.value != "codex":
            raise RuntimeAdmissionNotVerified("persistence_plan_invalid")
        return host.run(plan, tune)

    def execute_task_board(
        self, plan: Plan, settings: BoardSettings, host: BoardSession, proof: Verdict
    ) -> BoardResult:
        # Runs the ordered board only after its exact admission is verified.
        self._require_verdict(plan, proof)
        if plan.capability_id != "runtime.task-board@1" or plan.host.value != "codex":
            raise RuntimeAdmissionNotVerified("task_board_plan_invalid")
        return host.run(plan, settings, proof.admission_id)

    def _require_verdict(self, plan: Plan, verdict: Verdict | None) -> None:
        # Rejects absent, false, mismatched or empty receipts independently of command checks.
        if verdict is None or not verdict.admitted:
            raise RuntimeAdmissionNotVerified()
        if verdict.capability_id != plan.capability_id or not verdict.admission_id.strip():
            raise RuntimeAdmissionNotVerified()
