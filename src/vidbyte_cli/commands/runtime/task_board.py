"""Validates and admits one sequential task-board run over separate Codex agents.

Each task runs in its own agent with windowed summaries of prior results.
The command validates locally, buys admission, verifies the grant, then runs offline.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import click

from ...lib.constants.runtime import TaskBoardProgress as Progress
from ...lib.errors.failures import RuntimeAdmissionNotVerified
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Context
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...lib.runtime_primitives.task_board import TaskBoardCodexSession
from ...types.provider import PROVIDER_ENV_VARS, Provider
from ...types.runtime import (
    RuntimeAdmissionRequest,
    RuntimeGrantVerificationRequest,
    RuntimeHost,
    TaskBoardSettings,
    TaskBoardSummaryMode,
)


class TaskBoardCommand:
    """Keeps board validation and provider credentials ahead of paid admission."""

    def register(self, parent: click.Group) -> None:
        # Attaches task-board with window and summary controls as rich options.
        @parent.command(
            name="task-board", help="Run an ordered task board with per-task Codex agents"
        )
        @click.argument("tasks", nargs=-1)
        @click.option(
            "--tasks-file",
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            default=None,
            help="File with one board task per line; blank lines are skipped.",
        )
        @click.option(
            "--host",
            type=click.Choice(("auto", "codex")),
            default="codex",
            show_default=True,
            help="Native host for every board task agent; only codex is supported in v1.",
        )
        @click.option(
            "--window",
            type=click.IntRange(0, 25),
            default=10,
            show_default=True,
            help="How many prior task summaries the next agent sees; 0 means only its own task.",
        )
        @click.option(
            "--summary-mode",
            type=click.Choice(("truncate-tail", "head-tail")),
            default="truncate-tail",
            show_default=True,
            help=("Summary shape per prior result: truncate-tail prefix or head-tail."),
        )
        @click.option(
            "--summary-max-chars",
            type=click.IntRange(100, 8000),
            default=1200,
            show_default=True,
            help="Max characters kept per prior result summary before markers are added.",
        )
        @click.option(
            "--stop-on-error/--no-stop-on-error",
            default=True,
            show_default=True,
            help="Stop at the first failed task instead of marking it failed and continuing.",
        )
        @click.option(
            "--retries-per-task",
            type=click.IntRange(0, 3),
            default=1,
            show_default=True,
            help="Retries for one task with the same windowed prompt before it counts as failed.",
        )
        @click.option(
            "--idempotency-key", "key", default=None, help="Reuse only to recover admission."
        )
        @click.pass_obj
        def _run(
            ctx: Context,
            tasks: tuple[str, ...],
            tasks_file: Path | None,
            host: str,
            window: int,
            summary_mode: str,
            summary_max_chars: int,
            stop_on_error: bool,
            retries_per_task: int,
            key: str | None,
        ) -> None:
            # Delegates parsed values to the class-owned execution method.
            self.execute(
                ctx,
                tasks,
                tasks_file,
                host,
                window,
                summary_mode,
                summary_max_chars,
                stop_on_error,
                retries_per_task,
                key,
            )

    def execute(
        self,
        context: Context,
        tasks: tuple[str, ...],
        tasks_file: Path | None,
        host: str,
        window: int,
        summary_mode: str,
        summary_max_chars: int,
        stop_on_error: bool,
        retries_per_task: int,
        key: str | None,
    ) -> None:
        # Resolves board input locally before any wallet admission, then verifies before execution.
        progress = context.output().diagnostic
        progress(Progress.PREPARING)
        key = self._idempotency_key(key)
        board = self._board_tasks(tasks, tasks_file)
        requested = None if host == "auto" else RuntimeHost(host)
        plan = context.runtime_launch_planner().build_task_board(board, requested, Path.cwd())
        settings = self._settings(
            board, window, summary_mode, summary_max_chars, stop_on_error, retries_per_task
        )
        progress(Progress.CREDENTIALS)
        session = self._session(context)
        session.prepare(plan)
        endpoints = context.runtime_endpoints()
        progress(Progress.ADMISSION)
        grant = endpoints.admit_task_board(RuntimeAdmissionRequest(host=plan.host), key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        progress(Progress.VERIFYING)
        verified = endpoints.verify_grant(
            RuntimeGrantVerificationRequest(
                grant_token=grant.grant_token,
                idempotency_key_hash=RuntimeAdmissionGate.hash_idempotency_key(key),
            )
        )
        verdict = RuntimeAdmissionGate().verify_online(plan, grant, verified)
        if not verdict.admitted:
            raise RuntimeAdmissionNotVerified(verdict.reason)
        progress(Progress.ADMITTED)
        result = context.runtime_executor().execute_task_board(plan, settings, session, verdict)
        context.output().result(
            OutputDocument(kind="runtime.task-board", data=result.model_dump(mode="json")),
            result.text,
        )

    def _board_tasks(self, tasks: tuple[str, ...], tasks_file: Path | None) -> tuple[str, ...]:
        # Merges CLI tasks with file tasks while preserving board order.
        collected = [task for task in (item.strip() for item in tasks) if task]
        if tasks_file is not None:
            collected.extend(
                line
                for line in (
                    part.strip() for part in tasks_file.read_text(encoding="utf-8").splitlines()
                )
                if line
            )
        return tuple(collected)

    def _settings(
        self,
        board: tuple[str, ...],
        window: int,
        summary_mode: str,
        summary_max_chars: int,
        stop_on_error: bool,
        retries_per_task: int,
    ) -> TaskBoardSettings:
        # Constructs frozen board settings with validated summary behavior.
        mode = (
            TaskBoardSummaryMode.HEAD_TAIL
            if summary_mode == "head-tail"
            else TaskBoardSummaryMode.TRUNCATE_TAIL
        )
        return TaskBoardSettings(
            tasks=board,
            window=window,
            summary_mode=mode,
            summary_max_chars=summary_max_chars,
            stop_on_error=stop_on_error,
            max_retries_per_task=retries_per_task,
        )

    def _idempotency_key(self, key: str | None) -> str:
        # Validates the replay-safe admission key before any local planning.
        candidate = key or str(uuid4())
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", candidate) is None:
            raise click.BadParameter(
                "Use 8–128 letters, digits, dots, underscores, colons or hyphens."
            )
        return candidate

    def _session(self, context: Context) -> TaskBoardCodexSession:
        # Filters parent secrets so the child Codex process inherits only its key.
        credentials = context.require_provider_credentials(Provider.OPENAI)
        environment = dict(context.environment)
        for name in (
            *PROVIDER_ENV_VARS.values(),
            "GOOGLE_API_KEY",
            "VIDBYTE_API_KEY",
            "RUNTIME_ADMISSION_SIGNING_KEY",
            "CODEX_API_KEY",
        ):
            environment[name] = ""
        environment["OPENAI_API_KEY"] = credentials.secret_value()
        return TaskBoardCodexSession(environment, context.output().diagnostic)
