"""Validates and admits one sequential task-board run over separate Codex agents.

Each task runs in its own agent, optionally reading bounded summaries of the tasks just
before it. The command validates locally, buys admission, verifies the grant, then runs
offline. A board is built from literal task arguments or from whole Markdown files, never
from both.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import click

from ...lib.constants.runtime import TaskBoardProgress as Progress
from ...lib.errors.failures import (
    RuntimeAdmissionNotVerified,
    TaskBoardInputInvalid,
    TaskBoardTaskFileInvalid,
)
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Context
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...lib.runtime_primitives.task_board import TaskBoardCodexSession
from ...types.provider import PROVIDER_ENV_VARS, Provider
from ...types.runtime import (
    RuntimeAdmissionRequest,
    RuntimeGrantVerificationRequest,
    RuntimeHost,
    TaskBoardContextMode,
    TaskBoardSettings,
    TaskBoardSummaryMode,
)

_COMMAND_HELP = (
    "Run an ordered board of tasks, each in its own Codex agent, on this machine. Give the "
    "board either as literal TASKS arguments, where every argument is one complete task "
    "statement in board order, or as repeated --task-file paths, where each whole Markdown "
    "file is one task; the two forms cannot be mixed because that would leave board order "
    "ambiguous. Tasks always run strictly in the order given, one at a time, and each agent "
    "is thrown away when its task ends so no thread is ever reused. By default an agent also "
    "reads bounded summaries of the few tasks immediately before it, which you can narrow "
    "with --window or switch off entirely with --context-mode isolated. Vidbyte charges two "
    "cents to admit the whole run and every model call is billed to your own OpenAI account. "
    "With --allow-decompose an agent may instead replace its own task with an array of "
    "subtasks at its index, in which case every agent sees only its own task."
)
_TASK_FILE_HELP = (
    "Path to one Markdown file whose entire contents are a single board task. Repeat the "
    "option once per task, in the order the tasks should run, when a task is too long or too "
    "structured to pass as a shell argument. The file is read whole and used verbatim, so its "
    "headings, lists, and blank lines all reach the agent exactly as written, and its own "
    "lines are never split into separate tasks. Each path must end in .md and hold something "
    "other than whitespace, and this option cannot be combined with literal TASKS arguments."
)
_HOST_HELP = (
    "Which installed native coding agent runs every task on this board. Only codex is "
    "supported in v1, so this option exists to make the host explicit in scripts and to keep "
    "the flag stable as more hosts are admitted later. Passing auto asks the CLI to resolve "
    "whichever supported host it can find on PATH, which today can only ever resolve to "
    "codex. The backend refuses admission for any other host, so an unavailable or "
    "unsupported host fails before payment rather than part-way through the board."
)
_WINDOW_HELP = (
    "How many immediately preceding task results an agent may read, counted backwards from "
    "the task about to run. With the default of 10, the agent for task 90 receives summaries "
    "of tasks 80 through 89 and nothing earlier, which is what keeps prompt size flat however "
    "long the board grows. A window of 0 leaves an agent with only its own task while still "
    "telling it that earlier tasks ran, and a window larger than the number of finished tasks "
    "simply clamps to what exists. This option is ignored when --context-mode is isolated."
)
_CONTEXT_MODE_HELP = (
    "Whether an agent is told anything at all about the tasks that ran before it. In "
    "windowed-summaries mode, the default, each agent reads bounded summaries of the previous "
    "--window results, which is what you want when later tasks build on earlier ones. In "
    "isolated mode no prior result reaches any agent and the prompt carries no prior-results "
    "section whatsoever, which is the correct choice for a board of independently decomposed "
    "tasks that must not inherit each other's assumptions. Isolated mode overrides --window, "
    "--summary-mode, and --summary-max-chars instead of combining with them."
)
_SUMMARY_MODE_HELP = (
    "The shape of each prior-result summary once that result is longer than "
    "--summary-max-chars. truncate-tail keeps the opening of the result and names how many "
    "characters were dropped, which favors a task's setup and reasoning. head-tail splits the "
    "budget evenly between the opening and the closing of the result, which is what preserves "
    "a concluding answer or a final file listing. Neither mode calls a model, so "
    "summarization stays deterministic and costs nothing, and both are ignored when "
    "--context-mode is isolated."
)
_SUMMARY_MAX_CHARS_HELP = (
    "The character budget for one prior-result summary before --summary-mode starts dropping "
    "content. A result at or under this length is passed forward untouched, and anything "
    "longer is shortened and marked with the exact number of characters removed. Multiply "
    "this budget by --window to predict the worst-case size of the prior-results block a "
    "single agent will read. Accepted values run from 100 to 8000 characters, and the setting "
    "is ignored when --context-mode is isolated."
)
_STOP_ON_ERROR_HELP = (
    "What the board does the first time a task exhausts its retries. With --stop-on-error, "
    "the default, the board halts immediately, keeps every result completed before the "
    "failure, and returns that prefix rather than running work that depends on a task which "
    "never finished. With --no-stop-on-error the failed task is recorded with a failed "
    "status, a short placeholder stands in for its summary so board indices stay aligned, and "
    "the next task starts anyway. Keep the default for a board whose tasks depend on each "
    "other, and turn it off for independent tasks where one failure should not cancel the rest."
)
_RETRIES_PER_TASK_HELP = (
    "How many extra attempts one task receives after its first attempt fails, before the "
    "board treats that task as failed. Every retry sends the identical prompt to a brand-new "
    "agent, so a retry recovers from a crashed or timed-out host rather than from a task the "
    "agent understood but could not do. Each attempt is billed to your own OpenAI account, so "
    "a high retry count on a large board multiplies model cost even though the Vidbyte "
    "admission is charged once. Accepted values run from 0 to 3, and a task that succeeds on "
    "a retry produces exactly one result entry, never a duplicate."
)
_IDEMPOTENCY_KEY_HELP = (
    "A caller-supplied key that makes the paid admission for this run replay-safe. Leave it "
    "unset and the CLI generates a fresh key, which is correct for every new board. Reuse the "
    "key from an earlier invocation only to recover an admission whose response you never "
    "saw, so the wallet is not charged a second time for the same run. Reusing a key does not "
    "resume or deduplicate the board itself: the tasks run again from index 0, and every "
    "model call is billed to your own OpenAI account again."
)
_ALLOW_DECOMPOSE_HELP = (
    "Whether the agent for one task may replace that task with an array of subtasks at its "
    "own index. With --allow-decompose every agent sees only its own task and never reads "
    "sibling tasks or prior summaries, so each split decision stays local to the work being "
    "divided. A parent that returns subtasks is replaced in place: three subtasks from task "
    "1 turn a 3-task board into 5 tasks occupying positions 1, 2, and 3. Children never "
    "decompose further, and the --window and summary options are ignored while this mode "
    "is on."
)
_MAX_SUBTASKS_HELP = (
    "How many subtasks one parent task may expand into when decomposition is allowed. Each "
    "candidate must be a self-contained task string the session validates before splicing, "
    "and duplicates collapse to their first occurrence so the board never grows with "
    "repeated work. A parent that returns fewer than two valid candidates keeps its normal "
    "completed result instead of decomposing. The whole board still caps at 500 tasks, so a "
    "splice that would overflow truncates to fit, and this option does nothing unless "
    "--allow-decompose is also passed."
)


class TaskBoardCommand:
    """Keeps board validation and provider credentials ahead of paid admission."""

    def register(self, parent: click.Group) -> None:
        # Attaches task-board with window, context, and summary controls as rich options.
        @parent.command(name="task-board", help=_COMMAND_HELP)
        @click.argument("tasks", nargs=-1)
        @click.option(
            "--task-file",
            "task_files",
            multiple=True,
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            help=_TASK_FILE_HELP,
        )
        @click.option(
            "--host",
            type=click.Choice(("auto", "codex")),
            default="codex",
            show_default=True,
            help=_HOST_HELP,
        )
        @click.option(
            "--window",
            type=click.IntRange(0, 25),
            default=10,
            show_default=True,
            help=_WINDOW_HELP,
        )
        @click.option(
            "--context-mode",
            type=click.Choice(("windowed-summaries", "isolated")),
            default="windowed-summaries",
            show_default=True,
            help=_CONTEXT_MODE_HELP,
        )
        @click.option(
            "--summary-mode",
            type=click.Choice(("truncate-tail", "head-tail")),
            default="truncate-tail",
            show_default=True,
            help=_SUMMARY_MODE_HELP,
        )
        @click.option(
            "--summary-max-chars",
            type=click.IntRange(100, 8000),
            default=1200,
            show_default=True,
            help=_SUMMARY_MAX_CHARS_HELP,
        )
        @click.option(
            "--stop-on-error/--no-stop-on-error",
            default=True,
            show_default=True,
            help=_STOP_ON_ERROR_HELP,
        )
        @click.option(
            "--retries-per-task",
            type=click.IntRange(0, 3),
            default=1,
            show_default=True,
            help=_RETRIES_PER_TASK_HELP,
        )
        @click.option(
            "--allow-decompose/--no-allow-decompose",
            default=False,
            show_default=True,
            help=_ALLOW_DECOMPOSE_HELP,
        )
        @click.option(
            "--max-subtasks",
            type=click.IntRange(2, 10),
            default=5,
            show_default=True,
            help=_MAX_SUBTASKS_HELP,
        )
        @click.option("--idempotency-key", "key", default=None, help=_IDEMPOTENCY_KEY_HELP)
        @click.pass_obj
        def _run(
            ctx: Context,
            tasks: tuple[str, ...],
            task_files: tuple[Path, ...],
            host: str,
            window: int,
            context_mode: str,
            summary_mode: str,
            summary_max_chars: int,
            stop_on_error: bool,
            retries_per_task: int,
            allow_decompose: bool,
            max_subtasks: int,
            key: str | None,
        ) -> None:
            # Delegates parsed values to the class-owned execution method.
            self.execute(
                ctx,
                tasks,
                task_files,
                host,
                window,
                context_mode,
                summary_mode,
                summary_max_chars,
                stop_on_error,
                retries_per_task,
                allow_decompose,
                max_subtasks,
                key,
            )

    def execute(
        self,
        context: Context,
        tasks: tuple[str, ...],
        task_files: tuple[Path, ...],
        host: str,
        window: int,
        context_mode: str,
        summary_mode: str,
        summary_max_chars: int,
        stop_on_error: bool,
        retries_per_task: int,
        allow_decompose: bool,
        max_subtasks: int,
        key: str | None,
    ) -> None:
        # Everything before ADMISSION is free, so every rejection a caller can cause happens
        # before the wallet is touched, and execution happens only after the grant is verified.
        progress = context.output().diagnostic
        progress(Progress.PREPARING)
        # The key is validated first because an invalid one would otherwise surface only after
        # the board has been read from disk and a host has been resolved.
        key = self._idempotency_key(key)
        # Resolving the board is the one step that reads caller files; it fails closed on a
        # mixed, empty, non-Markdown, or unreadable source.
        board = self._board_tasks(tasks, task_files)
        requested = None if host == "auto" else RuntimeHost(host)
        # The plan carries only a board label, never the task text: task content is local and
        # must not travel to the backend with the admission request.
        plan = context.runtime_launch_planner().build_task_board(board, requested, Path.cwd())
        settings = self._settings(
            board,
            window,
            context_mode,
            summary_mode,
            summary_max_chars,
            stop_on_error,
            retries_per_task,
            allow_decompose,
            max_subtasks,
        )
        if allow_decompose:
            progress("Decomposition is on: agents see only their own task; window context is off.")
        progress(Progress.CREDENTIALS)
        # Building the session imports the SDK and filters the child environment, so a missing
        # SDK or a missing provider key also fails before payment.
        session = self._session(context)
        session.prepare(plan)
        endpoints = context.runtime_endpoints()
        progress(Progress.ADMISSION)
        # One flat admission covers the whole board, however many tasks it holds.
        grant = endpoints.admit_task_board(RuntimeAdmissionRequest(host=plan.host), key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        progress(Progress.VERIFYING)
        # The grant is re-read from the backend rather than trusted as returned, and the key
        # hash ties that verification to this exact invocation.
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
        # The runner receives the verified verdict and no endpoints at all, which is what keeps
        # the network out of task execution.
        result = context.runtime_executor().execute_task_board(plan, settings, session, verdict)
        # Only the board result reaches stdout; every phase line above went to stderr.
        context.output().result(
            OutputDocument(kind="runtime.task-board", data=result.model_dump(mode="json")),
            result.text,
        )

    def _board_tasks(self, tasks: tuple[str, ...], task_files: tuple[Path, ...]) -> tuple[str, ...]:
        # A board comes from exactly one source: literal task strings, or whole Markdown files
        # one task each. Accepting both at once would leave the board's order ambiguous.
        literals = tuple(item for item in (task.strip() for task in tasks) if item)
        if bool(literals) == bool(task_files):
            raise TaskBoardInputInvalid()
        if literals:
            return literals
        return tuple(self._file_task(path) for path in task_files)

    def _file_task(self, path: Path) -> str:
        # One whole file is one task, so its own line breaks are part of the task text and are
        # never treated as task separators.
        if path.suffix.lower() != ".md":
            raise TaskBoardTaskFileInvalid()
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise TaskBoardTaskFileInvalid() from error
        if not text:
            raise TaskBoardTaskFileInvalid()
        return text

    def _settings(
        self,
        board: tuple[str, ...],
        window: int,
        context_mode: str,
        summary_mode: str,
        summary_max_chars: int,
        stop_on_error: bool,
        retries_per_task: int,
        allow_decompose: bool,
        max_subtasks: int,
    ) -> TaskBoardSettings:
        # Constructs frozen board settings with validated context and summary behavior.
        mode = (
            TaskBoardSummaryMode.HEAD_TAIL
            if summary_mode == "head-tail"
            else TaskBoardSummaryMode.TRUNCATE_TAIL
        )
        sharing = (
            TaskBoardContextMode.ISOLATED
            if context_mode == "isolated"
            else TaskBoardContextMode.WINDOWED_SUMMARIES
        )
        return TaskBoardSettings(
            tasks=board,
            window=window,
            context_mode=sharing,
            summary_mode=mode,
            summary_max_chars=summary_max_chars,
            stop_on_error=stop_on_error,
            max_retries_per_task=retries_per_task,
            allow_decompose=allow_decompose,
            max_subtasks=max_subtasks,
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
