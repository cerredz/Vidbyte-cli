"""Versioned JSON documents validated by a caller-supplied pydantic model.

A command that keeps small structured records on disk — catalogs, indexes, per-item memory —
reads and writes them here, so bounding, parsing, model validation, containment of linked
names, and deterministic serialization are decided once. Bytes still move through
`LocalFileStore`; which model a document uses and what its fields mean stay with the caller.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..errors.failures import LocalDocumentInvalid, LocalFileReadFailed, LocalFileWriteFailed
from .store import LocalFileStore

DocumentT = TypeVar("DocumentT", bound=BaseModel)

DEFAULT_MAX_DOCUMENT_BYTES = 1_000_000


class LocalDocumentStore:
    """Reads, validates, atomically writes, and removes JSON documents under one root."""

    def __init__(self, root: Path, *, max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES) -> None:
        # The byte cap is per store so a caller holding tiny indexes can refuse a runaway file
        # before it is decoded, while the file store underneath keeps paths absolute.
        self._files = LocalFileStore(root)
        self._max_bytes = max_bytes

    @property
    def root(self) -> Path:
        # The absolute directory every document name resolves against.
        return self._files.root

    def path_of(self, name: str | Path) -> Path:
        # Names often come from another document (a catalog linking to a record), so a name
        # that is absolute, climbs with `..`, or resolves outside the root through a link is
        # refused rather than trusted.
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise LocalDocumentInvalid(relative.name, "its name leaves the document directory")
        candidate = self._files.path_of(relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise LocalDocumentInvalid(relative.name, "its name leaves the document directory")
        return candidate

    def exists(self, name: str | Path) -> bool:
        # Presence of a regular file or of a link at that name, since either would be replaced.
        path = self.path_of(name)
        return path.is_file() or path.is_symlink()

    def read(self, name: str | Path, model: type[DocumentT]) -> DocumentT | None:
        # None means absent and nothing else. A present document that is oversized, not JSON,
        # or not an instance of the model raises, so broken state is never read as empty state.
        path = self.path_of(name)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return None
        except OSError as error:
            raise LocalFileReadFailed(path.name, LocalFileStore.reason_for(error), error) from error
        if size > self._max_bytes:
            raise LocalDocumentInvalid(path.name, f"it exceeds {self._max_bytes} bytes")
        parsed = self._files.read_json(path)
        if parsed is None:
            return None
        try:
            return model.model_validate(parsed)
        except ValidationError as error:
            raise LocalDocumentInvalid(
                path.name, f"it does not match the {model.__name__} schema", error
            ) from error

    def write(self, name: str | Path, document: BaseModel) -> Path:
        # Sorted, indented, newline-terminated output keeps documents diffable by hand and
        # byte-stable across runs; the file store replaces the target atomically.
        path = self.path_of(name)
        body = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        return self._files.write_text(path, body)

    def remove(self, name: str | Path) -> None:
        # Used to roll back a document written earlier in the same mutation; an already absent
        # document is the desired end state, not a failure.
        path = self.path_of(name)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise LocalFileWriteFailed(
                path.name, LocalFileStore.reason_for(error), error
            ) from error
