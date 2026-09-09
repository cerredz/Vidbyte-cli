"""One board's checkpoint directory: its layout, its manifest, and its stored step chain.

A board is addressable by an absolute directory, so several boards coexist under one root and
a caller can name the one it means. Every byte written here goes through `TaskBoardFileStore`;
this class owns only board semantics — which file a step lives in, whether a stored board still
matches this invocation, how a fork copies a prefix, and how stored steps read back as a chain.
Nothing here touches the network; the backend never sees tasks.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ...types.runtime import (
    TaskBoardBoardSummary,
    TaskBoardCheckpoint,
    TaskBoardCheckpointChain,
    TaskBoardSettings,
)
from ..errors.failures import (
    TaskBoardBoardNotFound,
    TaskBoardCheckpointMismatch,
    TaskBoardCheckpointMissing,
)
from .task_board_files import TaskBoardFileStore

_MANIFEST_NAME = "board.json"
_MANIFEST_VERSION = 2
_EXPORT_NAME = "progress.jsonl"
_HOOK_TIMEOUT_SECONDS = 60


class TaskBoardCheckpointer:
    """Writes, loads, validates, forks, and reports one board's checkpoint directory."""

    def __init__(self, root: Path, board_id: str) -> None:
        # Building the store resolves the directory without creating it; writes create parents.
        self._store = TaskBoardFileStore(root / board_id)
        self._board_id = board_id

    @property
    def board_id(self) -> str:
        # The directory name identifying this board inside its checkpoint root.
        return self._board_id

    @property
    def directory(self) -> Path:
        # Absolute, so the path a result reports still resolves from another working directory.
        return self._store.root

    @staticmethod
    def board_id_for(tasks: tuple[str, ...]) -> str:
        # Hashes the joined tasks so an unchanged board reuses one directory.
        digest = hashlib.sha1("\x00".join(tasks).encode("utf-8")).hexdigest()
        return digest[:12]

    @staticmethod
    def timestamp() -> datetime:
        # Single clock call site so tests can compare created_at without freezing time.
        return datetime.now(UTC)

    def step_name(self, index: int) -> str:
        # One naming site for step files; the load glob and the fork copy both go through it.
        return f"step-{index}.json"

    def step_file(self, index: int) -> Path:
        # Absolute path to one step, which is what `show-step` hands back to its caller.
        return self._store.path_of(self.step_name(index))

    def write_manifest(
        self,
        settings: TaskBoardSettings,
        parent_board_id: str | None = None,
        forked_at_index: int | None = None,
    ) -> None:
        # Stores the whole task list, not just its hash, so a later resume, status, fork, or
        # export can address this board by id alone instead of re-supplying every task.
        payload: dict[str, object] = {
            "version": _MANIFEST_VERSION,
            "board_id": self._board_id,
            "tasks": list(settings.tasks),
            "parent_board_id": parent_board_id,
            "forked_at_index": forked_at_index,
            **self._fingerprint(settings),
        }
        self._store.write_json(_MANIFEST_NAME, payload)

    def read_manifest(self) -> dict[str, object]:
        # A board with no readable manifest is not a board; every read path fails closed here.
        manifest = self._store.read_json(_MANIFEST_NAME)
        if not isinstance(manifest, dict):
            raise TaskBoardBoardNotFound(self._board_id)
        return manifest

    def validate_manifest(self, settings: TaskBoardSettings) -> None:
        # Rejects a resumed board whose tasks or context settings differ from the stored run,
        # naming the first divergence rather than merging two boards into one history.
        try:
            manifest = self.read_manifest()
        except TaskBoardBoardNotFound as error:
            raise TaskBoardCheckpointMismatch("manifest-unreadable") from error
        for field, value in self._fingerprint(settings).items():
            if manifest.get(field) != value:
                raise TaskBoardCheckpointMismatch(field)

    def stored_tasks(self) -> tuple[str, ...]:
        # The board as it was checkpointed, which is what makes a resume command paste-able.
        tasks = self.read_manifest().get("tasks")
        if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
            raise TaskBoardCheckpointMismatch("manifest-tasks-unreadable")
        return tuple(str(task) for task in tasks)

    def write_step(self, record: TaskBoardCheckpoint) -> Path:
        # Persists one step atomically so a crash leaves at most one step unwritten.
        return self._store.write_json(self.step_name(record.index), record.model_dump(mode="json"))

    def read_step(self, index: int) -> TaskBoardCheckpoint:
        # A gap fails loudly, because silently re-running a step is what resume exists to avoid.
        raw = self._store.read_text(self.step_name(index))
        if raw is None:
            raise TaskBoardCheckpointMissing(index)
        try:
            return TaskBoardCheckpoint.model_validate_json(raw)
        except ValueError as error:
            raise TaskBoardCheckpointMismatch(f"step-{index}-unreadable") from error

    def load_prefix(self, count: int) -> tuple[TaskBoardCheckpoint, ...]:
        # Loads steps 0..count-1 in order; any gap fails instead of re-executing.
        return tuple(self.read_step(index) for index in range(count))

    def load_stored(self, task_count: int) -> tuple[TaskBoardCheckpoint, ...]:
        # Loads whatever exists without requiring a dense prefix, which is what a repair pass
        # and every read-only verb need: a board can legitimately be sparse after a replay.
        stored: list[TaskBoardCheckpoint] = []
        for index in range(task_count):
            if self._store.exists(self.step_name(index)):
                stored.append(self.read_step(index))
        return tuple(stored)

    def chain(self) -> TaskBoardCheckpointChain:
        # The stored steps as a linked list plus the fork edge to the board they branched from.
        manifest = self.read_manifest()
        count = manifest.get("task_count")
        task_count = count if isinstance(count, int) else 0
        parent = manifest.get("parent_board_id")
        forked = manifest.get("forked_at_index")
        return TaskBoardCheckpointChain(
            board_id=self._board_id,
            board_dir=str(self.directory),
            parent_board_id=parent if isinstance(parent, str) and parent else None,
            forked_at_index=forked if isinstance(forked, int) else None,
            task_count=task_count,
            nodes=self.load_stored(task_count),
        )

    def summary(self) -> TaskBoardBoardSummary:
        # One row of the board index, built from the same chain every other verb reads.
        chain = self.chain()
        return TaskBoardBoardSummary(
            board_id=chain.board_id,
            board_dir=chain.board_dir,
            task_count=chain.task_count,
            completed=len(chain.completed_indices),
            failed=len(chain.failed_indices),
            pending=len(chain.pending_indices),
            parent_board_id=chain.parent_board_id,
        )

    @classmethod
    def list_boards(cls, root: Path) -> tuple[TaskBoardBoardSummary, ...]:
        # Scans one checkpoint root. A directory without a readable manifest is skipped rather
        # than failing the listing, because an unrelated folder under the root is not an error.
        summaries: list[TaskBoardBoardSummary] = []
        for directory in TaskBoardFileStore(root).subdirectories():
            try:
                summaries.append(cls(root, directory.name).summary())
            except (TaskBoardBoardNotFound, TaskBoardCheckpointMismatch):
                continue
        return tuple(summaries)

    def resume_command(self, index: int, repair: bool = False) -> str:
        # One rendering site for the paste-able continuation, so every verb that returns one
        # returns the same shape. A board holding failures is repaired rather than resumed
        # past, because --from would re-pay for the completed steps between them.
        base = (
            "vidbyte-cli runtime task-board run "
            f"--checkpoint-root {self.directory.parent} --checkpoint-id {self._board_id}"
        )
        return f"{base} --from 0 --retry-failed-only" if repair else f"{base} --from {index}"

    def export_path(self, configured: str) -> Path:
        # An explicit path wins; otherwise the append-only log lives beside the step files.
        return Path(configured).expanduser().resolve() if configured else self._export_default()

    def append_export(self, record: TaskBoardCheckpoint, path: Path) -> Path:
        # One line per step, in completion order, so a forking tool reads the prefix by tailing
        # a single file rather than scanning and sorting a directory of step files.
        return self._store.append_line(path, record.model_dump_json())

    def write_report(self, chain: TaskBoardCheckpointChain, path: Path) -> Path:
        # A board's history as prose, for the reader who will never open a JSON step file.
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._report_body(chain), encoding="utf-8")
        return target

    def fork_into(self, target: TaskBoardCheckpointer, at_index: int) -> int:
        # Copies steps 0..at_index-1 into a new board and records the edge back to this one, so
        # both histories stay independently readable and neither can overwrite the other.
        settings_manifest = self.read_manifest()
        copied = 0
        for index in range(at_index):
            name = self.step_name(index)
            if not self._store.exists(name):
                raise TaskBoardCheckpointMissing(index)
            self._store.copy_into(name, target.step_file(index))
            copied += 1
        forked: dict[str, object] = dict(settings_manifest)
        forked["board_id"] = target.board_id
        forked["parent_board_id"] = self._board_id
        forked["forked_at_index"] = at_index
        target.write_raw_manifest(forked)
        return copied

    def write_raw_manifest(self, payload: dict[str, object]) -> None:
        # Fork is the only caller: it carries a validated manifest across from another board
        # rather than rebuilding a fingerprint the source board already proved.
        self._store.write_json(_MANIFEST_NAME, payload)

    def run_hook(self, command: str, record: TaskBoardCheckpoint, step_file: Path) -> bool:
        # The hook is an observer, never a gate: its failure is reported and the board keeps
        # going, because a broken notification script must not cost a paid board its progress.
        environment = dict(os.environ)
        environment.update(
            {
                "BOARD_DIR": str(self.directory),
                "BOARD_ID": self._board_id,
                "STEP_FILE": str(step_file),
                "STEP_INDEX": str(record.index),
                "STEP_STATUS": record.status,
            }
        )
        try:
            finished = subprocess.run(
                command,
                shell=True,
                cwd=str(self.directory),
                env=environment,
                timeout=_HOOK_TIMEOUT_SECONDS,
                check=False,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return finished.returncode == 0

    def _export_default(self) -> Path:
        # Keeps the log inside the board it describes when the caller names no path.
        return self._store.path_of(_EXPORT_NAME)

    def _fingerprint(self, settings: TaskBoardSettings) -> dict[str, object]:
        # The settings a stored step's prompt actually depends on. Two runs that agree here
        # produce the same prompts, which is exactly what resume and replay promise. Run
        # controls such as the resume point, budgets, or the checkpoint mode are deliberately
        # absent: they change per invocation, and would reject every legitimate resume.
        return {
            "task_hash": self.board_id_for(settings.tasks),
            "task_count": len(settings.tasks),
            "window": settings.window,
            "context_mode": settings.context_mode.value,
            "summary_mode": settings.summary_mode.value,
            "summary_max_chars": settings.summary_max_chars,
            "handoff_mode": settings.handoff_mode.value,
        }

    def _report_body(self, chain: TaskBoardCheckpointChain) -> str:
        # Totals first, then one section per stored step in board order.
        spend = sum(node.estimated_cost_usd or 0.0 for node in chain.nodes)
        lines = [
            f"# Task board {chain.board_id}",
            "",
            f"- Directory: {chain.board_dir}",
            f"- Tasks: {chain.task_count}",
            f"- Completed: {len(chain.completed_indices)}",
            f"- Failed: {len(chain.failed_indices)}",
            f"- Pending: {len(chain.pending_indices)}",
            f"- Reported tokens: {chain.total_tokens}",
            f"- Estimated cost: ${spend:.4f}",
        ]
        if chain.parent_board_id is not None:
            lines.append(f"- Forked from {chain.parent_board_id} at step {chain.forked_at_index}")
        for node in sorted(chain.nodes, key=lambda item: item.index):
            tokens = "unreported" if node.total_tokens is None else str(node.total_tokens)
            lines.extend(
                [
                    "",
                    f"## Step {node.index} — {node.status}",
                    "",
                    f"- Thread: {node.thread_id}",
                    f"- Reported tokens: {tokens}",
                    "",
                    "### Task",
                    "",
                    node.task.strip(),
                    "",
                    "### Summary",
                    "",
                    node.summary.strip(),
                ]
            )
        return "\n".join(lines) + "\n"
