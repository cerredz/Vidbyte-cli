"""The explicit implementation boundary for local runtime algorithms.

This release cannot charge or launch accidentally: execution always raises before either
side effect. A later PR replaces only this class with admission and process orchestration.
"""

from __future__ import annotations

from typing import NoReturn

from ...types.runtime import PersistenceSettings, RuntimeLaunchPlan
from ..errors.failures import (
    PersistenceExecutionNotImplemented,
    RuntimeAdmissionNotVerified,
    RuntimeExecutionNotImplemented,
)


class RuntimeExecutor:
    """Guards the absent runtime implementation from accidental paid execution."""

    def execute_adversarial_team(self, plan: RuntimeLaunchPlan, verdict=None) -> NoReturn:  # type: ignore[no-untyped-def]
        # Requires a successful layered gate verdict before any agent could be spawned.
        from ...types.runtime import RuntimeAdmissionVerdict

        if verdict is None or not isinstance(verdict, RuntimeAdmissionVerdict) or not verdict.admitted:
            raise RuntimeAdmissionNotVerified()
        if verdict.capability_id != plan.capability_id or verdict.admission_id.strip() == "":
            raise RuntimeAdmissionNotVerified()
        raise RuntimeExecutionNotImplemented()

    def execute_persistence(
        self, plan: RuntimeLaunchPlan, settings: PersistenceSettings
    ) -> NoReturn:
        # Accepts the validated plan and settings only to fix the future implementation seam.
        del plan, settings
        raise PersistenceExecutionNotImplemented()
