"""Every disk operation the task board performs, behind one store rooted at one directory.

Checkpoint files, JSONL exports, Markdown reports, and task-list import and export all reach
the filesystem through this class, so atomicity, encoding, and path resolution are decided
once instead of at each call site. It knows paths and bytes only: which file a board step
belongs in is the checkpointer's decision, and what a task means is the command's.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from ..errors.failures import TaskBoardTaskFileInvalid, TaskBoardTaskListInvalid

_MARKDOWN_SUFFIXES = (".md", ".markdown")
_JSON_SUFFIXES = (".json",)


class TaskBoardFileStore:
    """Resolves, reads, and atomically writes every file one board directory owns."""

    def __init__(self, root: Path) -> None:
        # Resolving once at construction is what makes every path this store returns absolute,
        # which is the whole point: a board must stay addressable from another directory.
        self._root = root.expanduser().resolve()

    @property
    def root(self) -> Path:
        # The absolute directory every relative name in this store resolves against.
        return self._root

    def path_of(self, name: str) -> Path:
        # One join site, so no caller builds a board path by string concatenation.
        return self._root / name

    def exists(self, name: str) -> bool:
        # Presence check for a named file inside this store's root.
        return self.path_of(name).is_file()

    def subdirectories(self) -> tuple[Path, ...]:
        # Sorted so a board listing is stable across runs and filesystems.
        if not self._root.is_dir():
            return ()
        return tuple(sorted(child for child in self._root.iterdir() if child.is_dir()))

    def read_json(self, name: str) -> object | None:
        # Returns None for an absent or unparseable file; callers decide whether that is fatal.
        try:
            parsed: object = json.loads(self.path_of(name).read_text(encoding="utf-8"))
            return parsed
        except (OSError, ValueError):
            return None

    def read_text(self, name: str) -> str | None:
        # Text sibling of read_json for stored bodies that are not JSON documents.
        try:
            return self.path_of(name).read_text(encoding="utf-8")
        except OSError:
            return None

    def write_json(self, name: str, payload: object) -> Path:
        # Serializes first so a malformed payload fails before the target file is touched.
        return self.write_text(name, json.dumps(payload))

    def write_text(self, name: str, body: str) -> Path:
        # Writes through a temp sibling plus os.replace, so a reader never sees a partial file
        # and a crash mid-write leaves the previous version intact rather than a truncated one.
        target = self.path_of(name)
        temporary: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
            )
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(body)
            os.replace(temporary, target)
            return target
        except Exception:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            raise

    def append_line(self, path: Path, body: str) -> Path:
        # Append is deliberately not atomic: an export file is an ordered log that outside
        # tools tail, and rewriting it per step would break every reader holding an offset.
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{body}\n")
        return path

    def copy_into(self, name: str, destination: Path) -> Path:
        # Used by fork, which duplicates a stored prefix rather than moving or linking it, so
        # the original board stays readable and unchanged whatever the new one goes on to do.
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path_of(name), destination)
        return destination

    def read_task_file(self, path: Path) -> str:
        # One whole Markdown file is one task, so its own line breaks are part of the task text
        # and are never treated as task separators.
        if path.suffix.lower() not in _MARKDOWN_SUFFIXES:
            raise TaskBoardTaskFileInvalid()
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise TaskBoardTaskFileInvalid() from error
        if not text:
            raise TaskBoardTaskFileInvalid()
        return text

    def read_task_list(self, path: Path) -> tuple[str, ...]:
        # A whole board in one reviewable file. Markdown splits on level-two headings and JSON
        # is a flat array of strings; both keep board order exactly as the file lists it.
        suffix = path.suffix.lower()
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as error:
            raise TaskBoardTaskListInvalid() from error
        if suffix in _JSON_SUFFIXES:
            tasks = self._json_tasks(body)
        elif suffix in _MARKDOWN_SUFFIXES:
            tasks = self._markdown_tasks(body)
        else:
            raise TaskBoardTaskListInvalid()
        if not tasks:
            raise TaskBoardTaskListInvalid()
        return tasks

    def write_task_list(self, path: Path, tasks: tuple[str, ...]) -> Path:
        # Export is the exact inverse of import, so a written board reloads to the same tuple.
        suffix = path.suffix.lower()
        if suffix in _JSON_SUFFIXES:
            body = json.dumps(list(tasks), indent=2)
        elif suffix in _MARKDOWN_SUFFIXES:
            body = "".join(
                f"## Task {index}\n\n{task.strip()}\n\n" for index, task in enumerate(tasks)
            )
        else:
            raise TaskBoardTaskListInvalid()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _json_tasks(body: str) -> tuple[str, ...]:
        # A board file has to be a flat array of task strings; anything else is a different
        # document that would silently produce a board nobody wrote.
        try:
            parsed = json.loads(body)
        except ValueError as error:
            raise TaskBoardTaskListInvalid() from error
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise TaskBoardTaskListInvalid()
        return tuple(item.strip() for item in parsed if item.strip())

    @staticmethod
    def _markdown_tasks(body: str) -> tuple[str, ...]:
        # Level-two headings are the separator, and the heading line itself is dropped, so a
        # file's title and preamble above the first heading never become a task of their own.
        tasks: list[str] = []
        current: list[str] = []
        started = False
        for line in body.splitlines():
            if line.startswith("## "):
                if started and (task := "\n".join(current).strip()):
                    tasks.append(task)
                started, current = True, []
                continue
            if started:
                current.append(line)
        if started and (task := "\n".join(current).strip()):
            tasks.append(task)
        return tuple(tasks)
