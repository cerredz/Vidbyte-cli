"""FILE: src/vidbyte_cli/lib/harness/watcher.py

PURPOSE: Adapts generic harness run status to Poller and versioned transition output.

ROLE IN CODEBASE: BaseHarness and generic run commands delegate waiting here. Interrupted
or timed-out waits retain remote work and return an explicit status recovery command.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from ...types.harness import HarnessRun
from ..api.endpoints.harness import HarnessEndpoints
from ..errors import CliError, CliErrorCode
from ..output import OutputDocument, OutputManager
from ..polling import Poller, PollOptions, PollStopReason
from ..runtime.signals import CancellationSignal, SignalScope


class HarnessRunTarget:
    def __init__(self, endpoints: HarnessEndpoints, run_id: str) -> None:
        self._endpoints = endpoints
        self._run_id = run_id

    def fetch(self) -> HarnessRun:
        return self._endpoints.get_run(self._run_id)

    def is_terminal(self, value: HarnessRun) -> bool:
        return value.status in {"completed", "failed"}

    def fingerprint(self, value: HarnessRun) -> str:
        latest = value.events[-1].created_at if value.events else ""
        return f"{value.status}:{latest}"

    def suggested_delay(self, value: HarnessRun) -> float | None:
        del value
        return None


class HarnessRunObserver:
    def __init__(self, output: OutputManager) -> None:
        self._output = output

    def transition(self, value: HarnessRun) -> None:
        self._output.transition(
            OutputDocument(
                kind="harness.run.transition",
                data={"run_id": value.run_id, "status": value.status},
            ),
            f"Run {value.run_id}: {value.status}",
        )


class HarnessRunWatcher:
    def __init__(
        self,
        endpoints: HarnessEndpoints,
        output: OutputManager,
        poller: Poller | None = None,
    ) -> None:
        self._endpoints = endpoints
        self._output = output
        self._poller = poller or Poller()

    def watch(self, run_id: str, timeout_seconds: float | None = None) -> HarnessRun:
        cancellation = CancellationSignal()
        with SignalScope(cancellation):
            result = self._poller.watch(
                HarnessRunTarget(self._endpoints, run_id),
                HarnessRunObserver(self._output),
                PollOptions(timeout_seconds=timeout_seconds),
                cancellation,
            )
        if result.reason is PollStopReason.TERMINAL and result.value is not None:
            return result.value
        reason = "interrupted" if result.reason is PollStopReason.CANCELLED else "timed out"
        raise CliError(
            CliErrorCode.INTERRUPTED
            if result.reason is PollStopReason.CANCELLED
            else CliErrorCode.OPERATION_FAILED,
            f"The local wait {reason}; the remote harness run continues.",
            130 if result.reason is PollStopReason.CANCELLED else 1,
            hint=f"Run 'vidbyte-cli harness status {run_id}' to recover.",
        )
