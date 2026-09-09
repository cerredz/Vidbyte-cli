"""Atomic per-step task-board checkpoints under a local dot-directory.

One JSON file per step plus a manifest let a later invocation resume from an index or
replay a single step. Nothing here touches the network; the backend never sees tasks.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ...types.runtime import TaskBoardCheckpoint, TaskBoardSettings
from ..errors.failures import TaskBoardCheckpointMismatch, TaskBoardCheckpointMissing

_MANIFEST_NAME = "board.json"
_MANIFEST_VERSION = 1


class TaskBoardCheckpointer:
    """Writes, loads, and validates one board's checkpoint directory."""

    def __init__(self, root: Path, board_id: str) -> None:
        # Stores the board directory without creating it; writes create parents lazily.
        self._directory = root / board_id
        self._board_id = board_id

    @property
    def directory(self) -> Path:
        # Exposes the board directory so diagnostics can name it without rebuilding it.
        return self._directory

    @staticmethod
    def board_id_for(tasks: tuple[str, ...]) -> str:
        # Hashes the joined tasks so an unchanged board reuses one directory.
        digest = hashlib.sha1("\x00".join(tasks).encode("utf-8")).hexdigest()
        return digest[:12]

    def write_manifest(self, settings: TaskBoardSettings) -> None:
        # Records the board fingerprint every run so resume can reject drifted settings.
        payload = {
            "version": _MANIFEST_VERSION,
            "board_id": self._board_id,
            "task_hash": self.board_id_for(settings.tasks),
            "task_count": len(settings.tasks),
            "window": settings.window,
            "context_mode": settings.context_mode.value,
            "summary_mode": settings.summary_mode.value,
            "summary_max_chars": settings.summary_max_chars,
        }
        self._write_json(_MANIFEST_NAME, payload)

    def validate_manifest(self, settings: TaskBoardSettings) -> None:
        # Rejects a resumed board whose tasks or settings differ from the stored run.
        try:
            raw = (self._directory / _MANIFEST_NAME).read_text(encoding="utf-8")
            manifest = json.loads(raw)
        except (OSError, ValueError) as error:
            raise TaskBoardCheckpointMismatch("manifest-unreadable") from error
        if not isinstance(manifest, dict):
            raise TaskBoardCheckpointMismatch("manifest-unreadable")
        expected = {
            "task_hash": self.board_id_for(settings.tasks),
            "task_count": len(settings.tasks),
            "window": settings.window,
            "context_mode": settings.context_mode.value,
            "summary_mode": settings.summary_mode.value,
            "summary_max_chars": settings.summary_max_chars,
        }
        for field, value in expected.items():
            if manifest.get(field) != value:
                raise TaskBoardCheckpointMismatch(field)

    def write_step(self, record: TaskBoardCheckpoint) -> None:
        # Persists one step atomically so a crash leaves at most one step unwritten.
        self._write_json(f"step-{record.index}.json", record.model_dump(mode="json"))

    def load_prefix(self, count: int) -> tuple[TaskBoardCheckpoint, ...]:
        # Loads steps 0..count-1 in order; any gap fails instead of re-executing.
        records: list[TaskBoardCheckpoint] = []
        for index in range(count):
            try:
                raw = (self._directory / f"step-{index}.json").read_text(encoding="utf-8")
            except OSError as error:
                raise TaskBoardCheckpointMissing(index) from error
            try:
                records.append(TaskBoardCheckpoint.model_validate_json(raw))
            except ValueError as error:
                raise TaskBoardCheckpointMismatch(f"step-{index}-unreadable") from error
        return tuple(records)

    def _write_json(self, name: str, payload: object) -> None:
        # Writes through a temp sibling plus os.replace so readers never see partial files.
        tmp: str | None = None
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self._directory), prefix=f".{name}.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            os.replace(tmp, self._directory / name)
        except Exception:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            raise

    @staticmethod
    def timestamp() -> datetime:
        # Single clock call site so tests can compare created_at without freezing time.
        return datetime.now(UTC)
