"""Durable local storage for rules scans: one folder per scan under the CLI data directory.

A scan folder holds `manifest.json` (frozen scope, limits, batch plan, progress), one
`batch-NNNN.json` per finished batch, and `rules.md`. JSON goes through `LocalDocumentStore` and
the Markdown through `LocalFileStore`, so containment, size bounds, and atomic replacement are
decided once. Every storage failure leaves this class as `RulesScanStorageFailed`.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from ...lib.config.paths import VidbytePaths
from ...lib.constants.rules import RULES_SCAN_ID_PREFIX
from ...lib.errors.failures import (
    LocalDocumentInvalid,
    LocalFileReadFailed,
    LocalFileWriteFailed,
    RulesScanNotFound,
    RulesScanStorageFailed,
)
from ...lib.files.documents import LocalDocumentStore
from ...lib.files.store import LocalFileStore
from ...types.rules import RulesBatchRecord, RulesScanManifest

_MANIFEST = "manifest.json"
_DOCUMENT = "rules.md"
_SCAN_ID_RANDOM_BYTES = 4
ResultT = TypeVar("ResultT")


class RulesScanStore:
    """Reads and writes one user's rules scans."""

    def __init__(self, paths: VidbytePaths | None = None) -> None:
        # Paths stay injectable so tests never write into the real data directory.
        root = (paths or VidbytePaths.default()).rules_dir()
        self._documents = LocalDocumentStore(root)
        self._files = LocalFileStore(root)

    def create_scan_id(self) -> str:
        # Sortable by creation time and unique enough for one user's scans.
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"{RULES_SCAN_ID_PREFIX}_{stamp}_{secrets.token_hex(_SCAN_ID_RANDOM_BYTES)}"

    def scan_dir(self, scan_id: str) -> Path:
        # The absolute folder holding one scan's files.
        return self._files.path_of(scan_id).resolve()

    def save_manifest(self, manifest: RulesScanManifest) -> None:
        # Stamps the update time, then replaces the manifest atomically.
        manifest.updated_at = datetime.now(UTC)
        self._guard(lambda: self._documents.write(f"{manifest.scan_id}/{_MANIFEST}", manifest))

    def load_manifest(self, scan_id: str) -> RulesScanManifest:
        # Raises RulesScanNotFound when no manifest exists for the ID.
        manifest = self._guard(
            lambda: self._documents.read(f"{scan_id}/{_MANIFEST}", RulesScanManifest)
        )
        if manifest is None:
            raise RulesScanNotFound(scan_id)
        return manifest

    def save_batch(self, scan_id: str, record: RulesBatchRecord) -> None:
        # One document per finished batch, written before the manifest marks it complete.
        self._guard(
            lambda: self._documents.write(self._batch_name(scan_id, record.batch_index), record)
        )

    def load_batches(self, manifest: RulesScanManifest) -> list[RulesBatchRecord]:
        # Every recorded batch of a scan, in plan order.
        records: list[RulesBatchRecord] = []
        for index in sorted(manifest.completed_batches):
            record = self._read_batch(manifest.scan_id, index)
            if record is not None:
                records.append(record)
        return records

    def _read_batch(self, scan_id: str, index: int) -> RulesBatchRecord | None:
        # One stored batch record, or None when a batch finished without a record on disk.
        name = self._batch_name(scan_id, index)
        return self._guard(lambda: self._documents.read(name, RulesBatchRecord))

    def write_document(self, scan_id: str, body: str, extra_path: Path | None = None) -> Path:
        # Writes rules.md into the scan folder, plus a copy wherever the caller asked.
        path = self._guard(lambda: self._files.write_text(f"{scan_id}/{_DOCUMENT}", body))
        if extra_path is not None:
            copy = LocalFileStore(extra_path.resolve().parent)
            self._guard(lambda: copy.write_text(extra_path.name, body))
        return path.resolve()

    def read_document(self, scan_id: str) -> str | None:
        # The stored rules document, or None before the first document was written.
        return self._guard(lambda: self._files.read_text(f"{scan_id}/{_DOCUMENT}"))

    def list_manifests(self) -> list[RulesScanManifest]:
        # Every stored scan, newest first; unreadable folders are skipped rather than fatal.
        manifests: list[RulesScanManifest] = []
        for folder in self._guard(self._files.subdirectories):
            try:
                manifests.append(self.load_manifest(folder.name))
            except (RulesScanNotFound, RulesScanStorageFailed):
                continue
        return sorted(manifests, key=lambda item: item.created_at, reverse=True)

    @staticmethod
    def _batch_name(scan_id: str, index: int) -> str:
        # Zero-padded so a directory listing shows batches in order.
        return f"{scan_id}/batch-{index:04d}.json"

    @staticmethod
    def _guard(action: Callable[[], ResultT]) -> ResultT:
        # Converts every local file failure into this feature's one storage failure.
        try:
            return action()
        except (LocalDocumentInvalid, LocalFileReadFailed, LocalFileWriteFailed, OSError) as error:
            raise RulesScanStorageFailed(error) from error
