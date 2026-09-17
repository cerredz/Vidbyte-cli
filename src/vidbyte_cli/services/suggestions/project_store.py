"""Persists suggestion projects and explicit feedback in small local JSON documents.

The catalog contains project summaries and relative memory-file links, while each project
file contains its ordered feedback. The store performs validation before writes and uses the
CLI's atomic writer so a failed replacement does not leave truncated state.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ...lib.config import VidbytePaths
from ...lib.config.atomic import AtomicFileWriter
from ...types.suggestions import (
    FeedbackType,
    SuggestionFeedback,
    SuggestionProject,
    SuggestionProjectCatalog,
    SuggestionProjectMemory,
)

_MAX_DOCUMENT_BYTES = 1_000_000


class ProjectAlreadyExistsError(ValueError):
    """The requested project key is already present in the catalog."""


class ProjectNotFoundError(ValueError):
    """The requested project key is absent from the catalog."""


class ProjectStateError(ValueError):
    """An existing catalog or memory document could not be validated."""


class SuggestionProjectStore:
    """Reads and atomically updates the project catalog and linked memory files."""

    def __init__(
        self, paths: VidbytePaths | None = None, writer: AtomicFileWriter | None = None
    ) -> None:
        # Dependencies stay injectable so command tests never touch a user's data directory.
        self.paths = paths or VidbytePaths.default()
        self._writer = writer or AtomicFileWriter()

    def create(self, key: str, title: str, description: str) -> SuggestionProject:
        # Validates the new entry, writes its memory, then publishes the catalog link.
        if not isinstance(title, str) or not isinstance(description, str):
            raise ValueError("project title and description must be text")
        normalized_key = self._normalize_key(key)
        project = SuggestionProject(
            key=normalized_key,
            title=title.strip(),
            description=description.strip(),
            memory_file=f"projects/{normalized_key}.json",
        )
        catalog = self._read_catalog()
        if any(item.key == project.key for item in catalog.projects):
            raise ProjectAlreadyExistsError(project.key)
        memory_path = self._memory_path(project)
        if memory_path.exists() or memory_path.is_symlink():
            raise ProjectAlreadyExistsError(project.key)
        memory_created = True
        try:
            self._write_memory(memory_path, SuggestionProjectMemory(project_key=project.key))
            updated = catalog.model_copy(update={"projects": (*catalog.projects, project)})
            self._write_catalog(updated)
        except Exception:
            if memory_created:
                memory_path.unlink(missing_ok=True)
            raise
        return project

    def list(self) -> tuple[SuggestionProject, ...]:
        # Returns catalog entries in key order so human and machine output stay deterministic.
        return tuple(sorted(self._read_catalog().projects, key=lambda item: item.key))

    def get(self, key: str) -> SuggestionProject:
        # Resolves one exact key and rejects an unknown project without creating state.
        normalized = self._normalize_key(key)
        project = next(
            (item for item in self._read_catalog().projects if item.key == normalized), None
        )
        if project is None:
            raise ProjectNotFoundError(normalized)
        return project

    def load_memory(self, key: str) -> SuggestionProjectMemory:
        # Loads and validates the memory document linked by the catalog entry.
        project = self.get(key)
        memory = self._read_memory(self._memory_path(project))
        if memory.project_key != project.key:
            raise ValueError(f"project memory key does not match catalog: {project.key}")
        return memory

    def append_feedback(
        self, key: str, feedback_type: FeedbackType, suggestion: str, reason: str | None
    ) -> SuggestionFeedback:
        # Appends one explicit reaction while preserving every earlier feedback record.
        if not isinstance(suggestion, str) or (reason is not None and not isinstance(reason, str)):
            raise ValueError("feedback text and reason must be text")
        if not suggestion.strip():
            raise ValueError("feedback suggestion must be nonempty")
        project = self.get(key)
        memory_path = self._memory_path(project)
        memory = self.load_memory(project.key)
        record = SuggestionFeedback(
            type=feedback_type,
            suggestion=suggestion,
            reason=reason,
            created_at=(
                datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            ),
        )
        updated = memory.model_copy(update={"feedback": (*memory.feedback, record)})
        self._write_memory(memory_path, updated)
        return record

    def _read_catalog(self) -> SuggestionProjectCatalog:
        # Treats a missing first-run catalog as empty and validates every existing document.
        path = self.paths.suggestion_projects_file()
        if not path.exists():
            return SuggestionProjectCatalog()
        try:
            parsed = self._read_json(path)
            if not isinstance(parsed, dict) or parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported project catalog schema")
            return SuggestionProjectCatalog.model_validate(parsed)
        except (OSError, UnicodeError, ValueError, ValidationError) as error:
            raise ProjectStateError("project catalog") from error

    def _read_memory(self, path: Path) -> SuggestionProjectMemory:
        # Rejects a missing or malformed linked document instead of silently resetting history.
        try:
            parsed = self._read_json(path)
            if not isinstance(parsed, dict) or parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported project memory schema")
            return SuggestionProjectMemory.model_validate(parsed)
        except (OSError, UnicodeError, ValueError, ValidationError) as error:
            raise ProjectStateError("project memory") from error

    def _read_json(self, path: Path) -> object:
        # Reads a bounded UTF-8 JSON document without exposing its contents in errors.
        raw = path.read_bytes()
        if len(raw) > _MAX_DOCUMENT_BYTES:
            raise ValueError(f"project document exceeds {_MAX_DOCUMENT_BYTES} bytes")
        return json.loads(raw.decode("utf-8-sig"))

    def _write_catalog(self, catalog: SuggestionProjectCatalog) -> None:
        # Replaces the catalog through the shared private atomic writer.
        self._write_json(self.paths.suggestion_projects_file(), catalog.model_dump(mode="json"))

    def _write_memory(self, path: Path, memory: SuggestionProjectMemory) -> None:
        # Replaces one project's feedback document through the shared private atomic writer.
        self._write_json(path, memory.model_dump(mode="json"))

    def _write_json(self, path: Path, value: object) -> None:
        # Serializes only validated data and lets the writer create parent directories.
        encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self._writer.write(path, encoded)

    def _memory_path(self, project: SuggestionProject) -> Path:
        # Resolves the catalog link and prevents traversal outside the project-memory directory.
        relative = Path(project.memory_file)
        root = self.paths.suggestions_dir().resolve()
        memory_root = self.paths.suggestion_project_memory_dir().resolve()
        candidate = (root / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not candidate.is_relative_to(memory_root)
        ):
            raise ValueError(f"invalid project memory link: {project.key}")
        return candidate

    def _normalize_key(self, key: str) -> str:
        # Applies the same identifier rules before a key reaches validation or path handling.
        if not isinstance(key, str):
            raise ValueError("project key must be text")
        normalized = key.strip()
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", normalized) is None:
            raise ValueError(
                "project key must be 1-64 lowercase letters, numbers, hyphens, or underscores"
            )
        return normalized
