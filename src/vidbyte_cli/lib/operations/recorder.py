"""FILE: src/vidbyte_cli/lib/operations/recorder.py

PURPOSE: Adapts the concrete operation journal to a field-oriented recording interface so
application services do not construct persistence DTOs.

ROLE IN CODEBASE: Research composition passes this adapter through the OperationRecorder
port. OperationJournal continues to own atomic storage and schema validation.

ARCHITECTURE NOTE: The adapter accepts only hashes and recovery metadata. Request bodies,
prompts, provider keys, and authorization values have no parameter through which to enter
the journal.

TESTS: No feature tests are added under the approved no-tests workflow. The canonical
smoke and strict typing gates exercise construction.
"""

from __future__ import annotations

from .journal import OperationJournal, PendingOperation


class OperationJournalRecorder:
    """Field-oriented prompt-free adapter over OperationJournal."""

    def __init__(self, journal: OperationJournal) -> None:
        self._journal = journal

    def begin(
        self,
        operation_id: str,
        command: str,
        idempotency_key: str,
        request_fingerprint: str,
        recovery_command: str,
    ) -> None:
        # @intent prompt-free-recovery-record
        # The fingerprint proves request identity without persisting billable user input.
        self._journal.begin(
            PendingOperation(
                operation_id=operation_id,
                command=command,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                recovery_command=recovery_command,
            )
        )

    def accepted(
        self,
        operation_id: str,
        remote_id: str,
        recovery_command: str,
    ) -> None:
        self._journal.accepted(operation_id, remote_id, recovery_command)
