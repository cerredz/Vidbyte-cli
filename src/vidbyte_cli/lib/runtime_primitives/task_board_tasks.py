"""Board tasks as files: one-task Markdown files, and whole-board task lists in and out.

This is the task board's own format knowledge — which suffixes are accepted, how a Markdown
list splits into tasks, and what a JSON board looks like. The bytes themselves go through
`LocalFileStore`, so reading and writing behave exactly like every other local file the CLI
keeps. What a task means, and how a board runs, is decided elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors.failures import (
    LocalFileReadFailed,
    TaskBoardExportDestinationInvalid,
    TaskBoardTaskFileInvalid,
    TaskBoardTaskListInvalid,
)
from ..files import LocalFileStore

_MARKDOWN_SUFFIXES = (".md", ".markdown")
_JSON_SUFFIXES = (".json",)


class TaskBoardTaskFiles:
    """Reads board tasks from caller files and writes a stored board back out as one file."""

    def __init__(self) -> None:
        # Rooted at the working directory, so a relative caller path means what the caller's
        # shell meant by it; an absolute path passes through the store unchanged.
        self._store = LocalFileStore(Path.cwd())

    def read_task_file(self, path: Path) -> str:
        # One whole Markdown file is one task, so its own line breaks are part of the task text
        # and are never treated as task separators.
        if path.suffix.lower() not in _MARKDOWN_SUFFIXES:
            raise TaskBoardTaskFileInvalid()
        try:
            body = self._store.read_text(path)
        except LocalFileReadFailed as error:
            raise TaskBoardTaskFileInvalid() from error
        text = "" if body is None else body.strip()
        if not text:
            raise TaskBoardTaskFileInvalid()
        return text

    def read_task_list(self, path: Path) -> tuple[str, ...]:
        # A whole board in one reviewable file. Markdown splits on level-two headings and JSON
        # is a flat array of strings; both keep board order exactly as the file lists it.
        suffix = path.suffix.lower()
        try:
            body = self._store.read_text(path)
        except LocalFileReadFailed as error:
            raise TaskBoardTaskListInvalid() from error
        if body is None:
            raise TaskBoardTaskListInvalid()
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
        # A write failure surfaces as the store's own failure for the caller to put in context.
        suffix = path.suffix.lower()
        if suffix in _JSON_SUFFIXES:
            body = json.dumps(list(tasks), indent=2)
        elif suffix in _MARKDOWN_SUFFIXES:
            body = "".join(
                f"## Task {index}\n\n{task.strip()}\n\n" for index, task in enumerate(tasks)
            )
        else:
            raise TaskBoardExportDestinationInvalid()
        return self._store.write_text(path, body)

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
