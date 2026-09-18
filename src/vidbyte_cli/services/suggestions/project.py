"""Local suggestion projects: a catalog of keyed projects plus one feedback file per project.

`SuggestionProject` is the only place that decides what a project is, which file its memory
lives in, and how its title, description, and explicit feedback become run context. Reading,
validating, and atomically replacing the JSON documents is delegated to the general
`LocalDocumentStore`, so nothing here touches the filesystem directly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from ...lib.config import VidbytePaths
from ...lib.errors.failures import (
    LocalDocumentInvalid,
    LocalFileReadFailed,
    LocalFileWriteFailed,
    SuggestionProjectExists,
    SuggestionProjectNotFound,
    SuggestionProjectStateUnreadable,
    SuggestionProjectWriteFailed,
)
from ...lib.files import LocalDocumentStore
from ...types.suggestions import (
    FeedbackType,
    SuggestionFeedback,
    SuggestionFeedbackCapture,
    SuggestionProjectCatalog,
    SuggestionProjectMemory,
    SuggestionProjectRecord,
)

T = TypeVar("T")

_KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_CATALOG_NAME = "projects.json"
_MEMORY_DIRECTORY = "projects"
_MAX_TITLE_CHARS = 200
_MAX_DESCRIPTION_CHARS = 4000
_MAX_FEEDBACK_CHARS = 8192
_FEEDBACK_COMMAND = "vidbyte-cli agents suggest feedback"

PROJECT_CONTEXT_KIND = "project"
ACCEPTED_FEEDBACK_KIND = "accepted_feedback"
REJECTED_FEEDBACK_KIND = "rejected_feedback"


@dataclass(frozen=True, slots=True)
class SuggestionProjectKey:
    """One validated project selector, normalized once so every lookup compares equal text."""

    value: str

    def __post_init__(self) -> None:
        # Keys become file names, so the pattern is also what keeps a key from naming a path.
        if not isinstance(self.value, str):
            raise TypeError("project key must be text")
        normalized = self.value.strip()
        if _KEY_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "project key must be 1-64 lowercase letters, numbers, hyphens, or underscores"
            )
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class SuggestionProjectCreateInput:
    """Everything `create` needs, validated before any document is read."""

    key: SuggestionProjectKey
    title: str
    description: str

    def __post_init__(self) -> None:
        # Surrounding whitespace is not meaning, so it is trimmed before the bounds apply.
        title = self._bounded(self.title, "title", _MAX_TITLE_CHARS)
        description = self._bounded(self.description, "description", _MAX_DESCRIPTION_CHARS)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)

    @staticmethod
    def _bounded(value: str, name: str, limit: int) -> str:
        if not isinstance(value, str):
            raise TypeError(f"project {name} must be text")
        stripped = value.strip()
        if not stripped or len(stripped) > limit:
            raise ValueError(f"project {name} must be nonempty and at most {limit} characters")
        return stripped


@dataclass(frozen=True, slots=True)
class SuggestionFeedbackInput:
    """One explicit reaction to record, kept verbatim so the user's words are not rewritten."""

    key: SuggestionProjectKey
    feedback_type: FeedbackType
    suggestion: str
    reason: str | None = None

    def __post_init__(self) -> None:
        # Blank text is rejected, but surrounding spacing is preserved as the user supplied it.
        if not isinstance(self.suggestion, str) or not self.suggestion.strip():
            raise ValueError("suggestion must be nonempty")
        if len(self.suggestion) > _MAX_FEEDBACK_CHARS:
            raise ValueError(f"suggestion must be {_MAX_FEEDBACK_CHARS} characters or fewer")
        if self.reason is not None and (
            not isinstance(self.reason, str) or len(self.reason) > _MAX_FEEDBACK_CHARS
        ):
            raise ValueError(f"reason must be {_MAX_FEEDBACK_CHARS} characters or fewer")


class SuggestionProject:
    """Creates, looks up, and records feedback for local suggestion projects."""

    def __init__(self, paths: VidbytePaths | None = None) -> None:
        # Paths stay injectable so tests and commands never assume the user's data directory.
        root = (paths or VidbytePaths.default()).suggestions_dir()
        self._documents = LocalDocumentStore(root)

    def create(self, request: SuggestionProjectCreateInput) -> SuggestionProjectRecord:
        # Writes the memory file first and publishes the catalog link last, so a reader never
        # sees a catalog entry pointing at a file that does not exist yet.
        record = SuggestionProjectRecord(
            key=request.key.value,
            title=request.title,
            description=request.description,
            memory_file=f"{_MEMORY_DIRECTORY}/{request.key.value}.json",
        )
        catalog = self.catalog()
        if self.project_exists(request.key) or self._state(
            lambda: self._documents.exists(record.memory_file)
        ):
            raise SuggestionProjectExists(record.key)
        memory = SuggestionProjectMemory(project_key=record.key)
        self._mutate(lambda: self._documents.write(record.memory_file, memory))
        updated = catalog.model_copy(update={"projects": (*catalog.projects, record)})
        try:
            self._mutate(lambda: self._documents.write(_CATALOG_NAME, updated))
        except SuggestionProjectWriteFailed:
            # Rolls back the orphaned memory file so a retry with the same key can succeed.
            self._mutate(lambda: self._documents.remove(record.memory_file))
            raise
        return record

    def catalog(self) -> SuggestionProjectCatalog:
        # An absent catalog is the first-run state, not an error.
        stored = self._state(lambda: self._documents.read(_CATALOG_NAME, SuggestionProjectCatalog))
        return stored or SuggestionProjectCatalog()

    def list_projects(self) -> tuple[SuggestionProjectRecord, ...]:
        # Key order keeps human and machine listings deterministic.
        return tuple(sorted(self.catalog().projects, key=lambda item: item.key))

    def project_exists(self, key: SuggestionProjectKey) -> bool:
        return any(item.key == key.value for item in self.catalog().projects)

    def get_project(self, key: SuggestionProjectKey) -> SuggestionProjectRecord:
        # An unknown key is never created implicitly.
        found = next((item for item in self.catalog().projects if item.key == key.value), None)
        if found is None:
            raise SuggestionProjectNotFound(key.value)
        return found

    def project_metadata(self, key: SuggestionProjectKey) -> tuple[str, ...]:
        # Identity and scope reach the generator as ordinary labelled data.
        project = self.get_project(key)
        return (f"Project title: {project.title}", f"Project description: {project.description}")

    def get_project_feedback(self, key: SuggestionProjectKey) -> tuple[SuggestionFeedback, ...]:
        # A memory file missing or owned by another key means the catalog and disk disagree;
        # both refuse rather than silently resetting the project's history to empty.
        project = self.get_project(key)
        memory = self._state(
            lambda: self._documents.read(project.memory_file, SuggestionProjectMemory)
        )
        if memory is None:
            raise SuggestionProjectStateUnreadable("the linked project memory file is missing")
        if memory.project_key != project.key:
            raise SuggestionProjectStateUnreadable("the project memory key does not match")
        return memory.feedback

    def record_feedback(self, request: SuggestionFeedbackInput) -> SuggestionFeedback:
        # Appends after every earlier record; nothing is deduplicated or rewritten.
        project = self.get_project(request.key)
        history = self.get_project_feedback(request.key)
        record = SuggestionFeedback(
            type=request.feedback_type,
            suggestion=request.suggestion,
            reason=request.reason,
            created_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        memory = SuggestionProjectMemory(project_key=project.key, feedback=(*history, record))
        self._mutate(lambda: self._documents.write(project.memory_file, memory))
        return record

    def context_fields(self, key: SuggestionProjectKey) -> dict[str, tuple[str, ...]]:
        # Accepted and rejected reactions stay separate kinds so the service can suppress
        # rejected directions without re-reading which kind a sentence was.
        fields: dict[str, tuple[str, ...]] = {PROJECT_CONTEXT_KIND: self.project_metadata(key)}
        feedback = self.get_project_feedback(key)
        for feedback_type, kind in (
            (FeedbackType.ACCEPTED, ACCEPTED_FEEDBACK_KIND),
            (FeedbackType.REJECTED, REJECTED_FEEDBACK_KIND),
        ):
            rendered = tuple(item.context_text() for item in feedback if item.type is feedback_type)
            if rendered:
                fields[kind] = rendered
        return fields

    @staticmethod
    def feedback_capture(key: SuggestionProjectKey) -> SuggestionFeedbackCapture:
        # Gives a parent agent copyable commands for this project without implying feedback.
        options = f"--project {key.value} --suggestion '<text>' [--reason '<reason>']"
        return SuggestionFeedbackCapture(
            project_key=key.value,
            instruction=(
                "Call one command only after the user explicitly accepts or rejects a "
                "suggestion; do not infer feedback from silence or ambiguity."
            ),
            accept_command=f"{_FEEDBACK_COMMAND} accept {options}",
            reject_command=f"{_FEEDBACK_COMMAND} reject {options}",
        )

    def _state(self, read: Callable[[], T]) -> T:
        # One translation from the general store's failures to this feature's repair contract.
        try:
            return read()
        except (LocalFileReadFailed, LocalDocumentInvalid) as error:
            raise SuggestionProjectStateUnreadable(error.reason, error) from error

    def _mutate(self, write: Callable[[], T]) -> T:
        # A path refused before writing is invalid state; a refused write is a write failure.
        try:
            return write()
        except LocalDocumentInvalid as error:
            raise SuggestionProjectStateUnreadable(error.reason, error) from error
        except LocalFileWriteFailed as error:
            raise SuggestionProjectWriteFailed(error) from error


__all__ = [
    "ACCEPTED_FEEDBACK_KIND",
    "PROJECT_CONTEXT_KIND",
    "REJECTED_FEEDBACK_KIND",
    "SuggestionFeedbackInput",
    "SuggestionProject",
    "SuggestionProjectCreateInput",
    "SuggestionProjectKey",
]
