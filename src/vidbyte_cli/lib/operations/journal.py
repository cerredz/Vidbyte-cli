"""FILE: src/vidbyte_cli/lib/operations/journal.py

PURPOSE: Persists prompt-free local recovery records before remote mutations and marks
them accepted after a durable remote identity is returned.

ROLE IN CODEBASE: Generic harness and research mutation services use this journal so an
interruption leaves a safe recovery command without storing user prompt content.

ARCHITECTURE NOTE: One schema-versioned JSON file per operation is written atomically in
the platform state directory. Request fingerprints are hashes, never serialized bodies.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config.atomic import AtomicFileWriter
from ..config.paths import VidbytePaths
from ..errors import CliError, CliErrorCode


class PendingOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    operation_id: str = Field(min_length=8, max_length=128)
    command: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    recovery_command: str = Field(min_length=1, max_length=500)
    state: Literal["pending", "accepted"] = "pending"
    remote_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OperationJournal:
    """Atomic prompt-free recovery ledger."""

    def __init__(
        self,
        paths: VidbytePaths,
        writer: AtomicFileWriter | None = None,
    ) -> None:
        self._paths = paths
        self._writer = writer or AtomicFileWriter()

    def begin(self, record: PendingOperation) -> None:
        self._write(record)

    def accepted(
        self,
        operation_id: str,
        remote_id: str,
        recovery_command: str | None = None,
    ) -> PendingOperation:
        current = self.get(operation_id)
        updates: dict[str, object] = {"state": "accepted", "remote_id": remote_id}
        if recovery_command is not None:
            updates["recovery_command"] = recovery_command
        updated = current.model_copy(update=updates)
        self._write(updated)
        return updated

    def get(self, operation_id: str) -> PendingOperation:
        path = self._path(operation_id)
        try:
            return PendingOperation.model_validate_json(path.read_bytes())
        except (OSError, ValidationError) as error:
            raise CliError(
                CliErrorCode.OPERATION_FAILED,
                "The local operation recovery record is unavailable.",
                hint="Retry the original command with the same idempotency key.",
                cause=error,
            ) from error

    def _write(self, record: PendingOperation) -> None:
        encoded = record.model_dump_json(indent=2).encode("utf-8") + b"\n"
        self._writer.write(self._path(record.operation_id), encoded)

    def _path(self, operation_id: str) -> Path:
        if not 8 <= len(operation_id) <= 128:
            raise CliError(
                CliErrorCode.INTERNAL_ERROR,
                "An invalid local operation identifier was configured.",
                70,
            )
        filename = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return self._paths.operations_dir() / f"{filename}.json"
