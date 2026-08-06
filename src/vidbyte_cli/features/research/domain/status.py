"""FILE: src/vidbyte_cli/features/research/domain/status.py

PURPOSE: Centralizes terminal, resumable, successful, and optional shell-exit policy for
all known research run states.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from ....lib.errors.codes import ExitCode
from .models import ResearchStatus


class ResearchStatePolicy:
    _TERMINAL = frozenset(
        {
            ResearchStatus.COMPLETED,
            ResearchStatus.PARTIAL,
            ResearchStatus.FAILED,
            ResearchStatus.CANCELLED,
            ResearchStatus.CREDIT_EXHAUSTED,
        }
    )
    _RESUMABLE = frozenset(
        {
            ResearchStatus.PARTIAL,
            ResearchStatus.FAILED,
            ResearchStatus.CREDIT_EXHAUSTED,
        }
    )

    def is_terminal(self, status: ResearchStatus) -> bool:
        return status in self._TERMINAL

    def is_resumable(self, status: ResearchStatus) -> bool:
        return status in self._RESUMABLE

    def exit_code(self, status: ResearchStatus) -> int:
        if status is ResearchStatus.COMPLETED:
            return ExitCode.SUCCESS
        if status is ResearchStatus.PARTIAL:
            return ExitCode.PARTIAL_OUTCOME
        if status is ResearchStatus.CREDIT_EXHAUSTED:
            return ExitCode.CREDIT_EXHAUSTED
        return ExitCode.OPERATIONAL_FAILURE
