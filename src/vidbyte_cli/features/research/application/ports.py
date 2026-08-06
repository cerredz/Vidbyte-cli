"""FILE: src/vidbyte_cli/features/research/application/ports.py

PURPOSE: Defines the small idempotency and recovery-recording capabilities research use
cases need without importing filesystem infrastructure.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import Protocol


class IdempotencyProvider(Protocol):
    def create(self, explicit: str | None = None) -> str: ...


class OperationRecorder(Protocol):
    def begin(
        self,
        operation_id: str,
        command: str,
        idempotency_key: str,
        request_fingerprint: str,
        recovery_command: str,
    ) -> None: ...

    def accepted(
        self,
        operation_id: str,
        remote_id: str,
        recovery_command: str,
    ) -> None: ...
