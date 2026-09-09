"""Builds the local-only handoff for a future runtime executor.

The plan retains task and filesystem context in process memory. Nothing here contacts the
backend, serializes the environment, or launches an agent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ...types.runtime import RuntimeHost as Host
from ...types.runtime import RuntimeLaunchPlan as Plan
from ..constants.runtime import TaskBoardLimit
from ..errors.failures import (
    RuntimeHostUnavailable,
    RuntimeTaskInvalid,
    RuntimeWorkingDirectoryInvalid,
)
from .hosts import RuntimeHostRegistry

Product = Literal[
    "runtime.review.adversarial-team@1",
    "runtime.adversarial-team@1",
    "runtime.same-host-ensemble@1",
    "runtime.persistence@1",
    "runtime.task-board@1",
    "runtime.stages@1",
]


class RuntimeLaunchPlanner:
    """Validates local prerequisites and creates an inert launch plan."""

    def __init__(self, hosts: RuntimeHostRegistry) -> None:
        # Uses one registry so doctor and execution selection share host semantics.
        self._hosts = hosts

    def build(self, task: str, host: Host | None, cwd: Path, capability_id: Product) -> Plan:
        # Validates everything needed before a future paid admission can be requested.
        normalized_task = task.strip()
        if not normalized_task or len(task) > 20_000:
            raise RuntimeTaskInvalid()
        resolved_directory = cwd.resolve()
        if not resolved_directory.is_dir():
            raise RuntimeWorkingDirectoryInvalid()
        selected = self._hosts.resolve(host)
        if selected.executable is None:
            raise RuntimeHostUnavailable(selected.host.value)
        return Plan(
            capability_id=capability_id,
            host=selected.host,
            executable=Path(selected.executable),
            working_directory=resolved_directory,
            task=task,
        )

    def build_task_board(self, tasks: tuple[str, ...], host: Host | None, cwd: Path) -> Plan:
        # Validates board count and chars against the shared bounds, then builds a label-only
        # plan; the bounds live in TaskBoardLimit so the settings model cannot drift from here.
        if not tasks or len(tasks) > TaskBoardLimit.MAX_TASKS:
            raise RuntimeTaskInvalid()
        for task in tasks:
            if not task.strip() or len(task) > TaskBoardLimit.MAX_TASK_CHARS:
                raise RuntimeTaskInvalid()
        resolved_directory = cwd.resolve()
        if not resolved_directory.is_dir():
            raise RuntimeWorkingDirectoryInvalid()
        selected = self._hosts.resolve(host)
        if selected.executable is None:
            raise RuntimeHostUnavailable(selected.host.value)
        label = tasks[0][:200] if len(tasks[0]) > 200 else tasks[0]
        return Plan(
            capability_id="runtime.task-board@1",
            host=selected.host,
            executable=Path(selected.executable),
            working_directory=resolved_directory,
            task=f"Task board with {len(tasks)} tasks starting with: {label}",
        )
