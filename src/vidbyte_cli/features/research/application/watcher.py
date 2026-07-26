"""FILE: src/vidbyte_cli/features/research/application/watcher.py

PURPOSE: Adapts ResearchGateway run snapshots to generic Poller while keeping progress
presentation behind a transport- and CLI-independent observer port.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import Protocol

from ....lib.errors.cli_error import CliError
from ....lib.errors.codes import CliErrorCode
from ....lib.polling import Poller, PollOptions, PollStopReason
from ....lib.runtime.signals import CancellationSignal
from ..domain import ResearchGateway, ResearchRun, ResearchStatePolicy


class ResearchObserver(Protocol):
    def transition(self, run: ResearchRun) -> None: ...


class SilentResearchObserver:
    def transition(self, run: ResearchRun) -> None:
        del run


class ResearchRunTarget:
    def __init__(
        self,
        gateway: ResearchGateway,
        run_id: str,
        policy: ResearchStatePolicy,
    ) -> None:
        self._gateway = gateway
        self._run_id = run_id
        self._policy = policy

    def fetch(self) -> ResearchRun:
        return self._gateway.get_run(self._run_id)

    def is_terminal(self, value: ResearchRun) -> bool:
        return self._policy.is_terminal(value.status)

    def fingerprint(self, value: ResearchRun) -> str:
        return (
            f"{value.status}:{value.discovered_sources}:"
            f"{value.generated_artifacts}:{value.updated_at}"
        )

    def suggested_delay(self, value: ResearchRun) -> float | None:
        del value
        return None


class ResearchWatcher:
    """Watch one accepted research run without inferring remote cancellation."""

    def __init__(
        self,
        gateway: ResearchGateway,
        poller: Poller,
        observer: ResearchObserver | None = None,
        policy: ResearchStatePolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._poller = poller
        self._observer = observer or SilentResearchObserver()
        self._policy = policy or ResearchStatePolicy()

    def watch(
        self,
        run_id: str,
        timeout_seconds: float | None,
        cancellation: CancellationSignal | None = None,
    ) -> ResearchRun:
        signal = cancellation or CancellationSignal()
        result = self._poller.watch(
            ResearchRunTarget(self._gateway, run_id, self._policy),
            self._observer,
            PollOptions(timeout_seconds=timeout_seconds),
            signal,
        )
        if result.reason is PollStopReason.TERMINAL and result.value is not None:
            return result.value
        reason = "interrupted" if result.reason is PollStopReason.CANCELLED else "timed out"
        raise CliError(
            CliErrorCode.INTERRUPTED
            if result.reason is PollStopReason.CANCELLED
            else CliErrorCode.OPERATION_FAILED,
            f"The local research wait {reason}; the remote run continues.",
            130 if result.reason is PollStopReason.CANCELLED else 1,
            hint=f"Run 'vidbyte-cli research status {run_id}' to recover.",
        )
