"""The explicit implementation boundary for runtime algorithms that have none yet.

Only `adversarial-team` still lives here. `same-host-ensemble` graduated out of this class
in the ensemble implementation PR: it now runs in `services/ensemble/`, because a service
may depend on `lib/` but nothing in `lib/` may depend on a service.
"""

from __future__ import annotations

from typing import NoReturn

from ...types.runtime import RuntimeLaunchPlan
from ..errors.failures import (
    RuntimeAdmissionNotVerified,
    RuntimeExecutionNotImplemented,
)


class RuntimeExecutor:
    """Guards the absent adversarial-team implementation from accidental paid execution."""

    def execute_adversarial_team(self, plan: RuntimeLaunchPlan, verdict=None) -> NoReturn:  # type: ignore[no-untyped-def]
        # Requires a successful layered gate verdict before any agent could be spawned.
        from ...types.runtime import RuntimeAdmissionVerdict

        if verdict is None or not isinstance(verdict, RuntimeAdmissionVerdict) or not verdict.admitted:
            raise RuntimeAdmissionNotVerified()
        if verdict.capability_id != plan.capability_id or verdict.admission_id.strip() == "":
            raise RuntimeAdmissionNotVerified()
        raise RuntimeExecutionNotImplemented()
