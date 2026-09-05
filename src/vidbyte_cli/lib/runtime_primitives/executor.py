"""The explicit implementation boundary for runtime algorithms that have none yet.

Only `adversarial-team` still lives here. `same-host-ensemble` graduated out of this class
in the ensemble implementation PR: it now runs in `services/ensemble/`, because a service
may depend on `lib/` but nothing in `lib/` may depend on a service.
"""

from __future__ import annotations

from typing import NoReturn

from ...types.runtime import RuntimeLaunchPlan
from ..errors.failures import RuntimeExecutionNotImplemented


class RuntimeExecutor:
    """Guards the absent adversarial-team implementation from accidental paid execution."""

    def execute_adversarial_team(self, plan: RuntimeLaunchPlan) -> NoReturn:
        # Accepts the validated plan only to make the future implementation seam exact.
        del plan
        raise RuntimeExecutionNotImplemented()
