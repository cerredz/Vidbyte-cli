"""The explicit implementation boundary for local runtime algorithms.

This release cannot charge or launch accidentally: execution always raises before either
side effect. A later PR replaces only this class with admission and process orchestration.
"""

from __future__ import annotations

from typing import NoReturn

from ...types.runtime import RuntimeLaunchPlan
from ..errors.failures import RuntimeExecutionNotImplemented


class RuntimeExecutor:
    """Guards the absent runtime implementation from accidental paid execution."""

    def execute_adversarial_team(self, plan: RuntimeLaunchPlan) -> NoReturn:
        # Accepts the validated plan only to make the future implementation seam exact.
        del plan
        raise RuntimeExecutionNotImplemented()
