"""The task-board command group: running a board, and reading the boards already stored.

`run` validates locally, buys one admission, verifies the grant, then executes offline. Every
other verb here is free and offline: `list`, `status`, `show-step`, and `export-tasks` only
read a checkpoint directory, and `fork` only copies one. A board is built from literal task
arguments, whole Markdown files, one task-list file, or the task list a stored board recorded.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

import click

from ...lib.constants.runtime import TaskBoardProgress as Progress
from ...lib.errors.failures import RuntimeAdmissionNotVerified, TaskBoardInputInvalid
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Context
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...lib.runtime_primitives.task_board import TaskBoardCodexSession
from ...lib.runtime_primitives.task_board_checkpoints import TaskBoardCheckpointer
from ...lib.runtime_primitives.task_board_files import TaskBoardFileStore
from ...types.provider import PROVIDER_ENV_VARS, Provider
from ...types.runtime import (
    RuntimeAdmissionRequest,
    RuntimeGrantVerificationRequest,
    RuntimeHost,
    TaskBoardAgentSettings,
    TaskBoardCheckpoint,
    TaskBoardCheckpointChain,
    TaskBoardCheckpointMode,
    TaskBoardContextMode,
    TaskBoardForkResult,
    TaskBoardHandoffMode,
    TaskBoardListing,
    TaskBoardPromptPreview,
    TaskBoardReasoningEffort,
    TaskBoardRunControls,
    TaskBoardSandbox,
    TaskBoardSettings,
    TaskBoardStatusReport,
    TaskBoardStepDetail,
    TaskBoardSummaryMode,
    TaskBoardTaskExport,
)

_DEFAULT_CHECKPOINT_ROOT = Path(".vidbyte") / "task-board"
_BOARD_ID_PATTERN = r"[A-Za-z0-9._-]{1,64}"

_GROUP_HELP = (
    "Run an ordered board of tasks, each in its own Codex agent, and inspect the boards this "
    "machine has already stored. The run subcommand is the only one that costs anything: it "
    "buys one two-cent Vidbyte admission for the whole board and bills every model call to "
    "your own OpenAI account. Every other subcommand here reads or copies a checkpoint "
    "directory offline and for free, which is what makes it safe for an agent to call list, "
    "status, or show-step as often as it likes while deciding what to do next. Boards are "
    "addressed by a checkpoint root plus a board id, so several boards can exist side by side."
)
_COMMAND_HELP = (
    "Run an ordered board of tasks, each in its own Codex agent, on this machine. Give the "
    "board either as literal TASKS arguments, where every argument is one complete task "
    "statement in board order, as repeated --task-file paths, where each whole Markdown file "
    "is one task, or as a single --task-list file holding the whole board; these forms cannot "
    "be mixed because that would leave board order ambiguous, and a resume may instead reuse "
    "the task list its stored board recorded. Tasks always run strictly in the order given, "
    "one at a time, and each agent is thrown away when its task ends so no thread is ever "
    "reused. By default an agent also reads bounded summaries of the few tasks immediately "
    "before it, which you can narrow with --window or switch off entirely with --context-mode "
    "isolated. Vidbyte charges two cents to admit the whole run and every model call is billed "
    "to your own OpenAI account."
)
_LIST_HELP = (
    "List every checkpointed board stored under one checkpoint root, one line each. Each row "
    "reports the board id, its task count, how many steps completed, failed, and remain, and "
    "the absolute directory the board lives in. Reading a board runs no model turns and costs "
    "nothing, so an agent holding ten boards can call this freely to find the unfinished one. "
    "Use --checkpoint-root when the boards were saved somewhere other than the default "
    "directory, and follow up with status on whichever board id you want details for."
)
_STATUS_HELP = (
    "Report one stored board's progress without running or paying for anything. The result "
    "names which step indices completed, which failed, and which are still pending, along with "
    "the reported token total, the estimated spend, and the absolute board directory. It also "
    "returns a ready-to-paste resume command, so the decision to continue, repair, fork, or "
    "abandon can be made from facts rather than guesses. Pass --report-file to additionally "
    "write the same history out as a Markdown document a person can read."
)
_SHOW_STEP_HELP = (
    "Return everything stored for one board step in a single response. The record holds the "
    "absolute path of its checkpoint file, the full prompt the step received, its bounded "
    "summary, its status, its thread id, and its reported token count. Because all of it "
    "arrives together, debugging one step costs one call instead of several raw file reads. "
    "The step must already exist on disk, so run status first if you are unsure which indices "
    "this board has stored."
)
_FORK_HELP = (
    "Copy a stored board's first --at steps into a new board id and leave the original "
    "untouched. Forking is how you try two different endings from the same prefix: the copy "
    "gets its own directory, its own manifest, and a recorded edge back to the board it came "
    "from, so neither history can overwrite the other. Nothing runs and nothing is charged; "
    "the fork only duplicates checkpoint files that already exist. The result returns the new "
    "board's absolute directory and the resume command that continues it."
)
_EXPORT_TASKS_HELP = (
    "Write a stored board's task list back out as a reviewable file. Pass a .md destination to "
    "get one level-two section per task, or a .json destination to get a flat array of task "
    "strings; both round-trip exactly through --task-list. Exporting is how a board that "
    "started as shell arguments becomes a file you can commit, review, and re-run later. "
    "Nothing runs and nothing is charged, because this only reads the board manifest."
)
_TASK_FILE_HELP = (
    "Path to one Markdown file whose entire contents are a single board task. Repeat the "
    "option once per task, in the order the tasks should run, when a task is too long or too "
    "structured to pass as a shell argument. The file is read whole and used verbatim, so its "
    "headings, lists, and blank lines all reach the agent exactly as written, and its own "
    "lines are never split into separate tasks. Each path must end in .md and hold something "
    "other than whitespace, and this option cannot be combined with any other board source."
)
_TASK_LIST_HELP = (
    "Path to one file holding the whole board, so a hundred-task board is reviewable in git "
    "instead of pasted into a shell. A .md file is split on its level-two headings, one task "
    "per section with the heading line dropped, and a .json file is read as a flat array of "
    "task strings. Board order is exactly the order the file lists, and nothing is merged, "
    "reordered, or split further. This option cannot be combined with literal TASKS arguments "
    "or --task-file, and `export-tasks` writes the same two shapes back out."
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
    "--handoff, --summary-mode, and --summary-max-chars instead of combining with them."
)
_HANDOFF_HELP = (
    "What each finished task actually hands to the later tasks allowed to read it. In summary "
    "mode, the default, a reader sees only the bounded summary of each prior result, which is "
    "what keeps prompts flat on a long board. In task-and-summary mode every entry is prefixed "
    "with the prior task's own statement, so a reader learns what was asked as well as what "
    "came back, which helps when tasks are terse. In full-result mode the untruncated result "
    "text is forwarded instead, bounded only by the 20,000-character task ceiling, which is "
    "accurate but grows prompts fast and suits only short boards. It does nothing in isolated "
    "mode, and changing it invalidates a stored board for resume because prompts would differ."
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
_MODEL_HELP = (
    "Which Codex model every task agent on this board runs, given as the provider's own model "
    "identifier. Leaving it unset keeps whatever model the installed Codex host defaults to, "
    "which is the right choice when the board is not model-sensitive. Set it when a board "
    "needs a specific capability or price point, because one value applies to every iteration "
    "and no individual task can override it. The model is charged to your own OpenAI account "
    "rather than to the flat Vidbyte admission."
)
_SANDBOX_HELP = (
    "How much of the filesystem every task agent on this board may change. workspace-write, "
    "the default, lets a task edit files inside the working directory and is what a board of "
    "implementation tasks needs. read-only lets a task inspect the tree without writing to "
    "it, which is the correct setting for a board of review, audit, or planning tasks. "
    "full-access removes the sandbox entirely and should be reserved for boards whose tasks "
    "genuinely have to reach outside the workspace. One setting applies to the whole board."
)
_REASONING_EFFORT_HELP = (
    "How much reasoning each task turn asks the model to spend before answering. Leaving it "
    "unset keeps the provider default, which is what most boards want. Raising it to high or "
    "xhigh suits a board of a few genuinely hard tasks, while minimal or low suits a long "
    "board of mechanical ones. Effort multiplies your own provider bill on every task, so a "
    "500-task board at xhigh is a real cost decision rather than a tuning knob."
)
_TURN_TIMEOUT_HELP = (
    "How long one task attempt may run before the board cancels it and counts that attempt as "
    "failed. The default of five days is a ceiling on a wedged child process rather than a "
    "budget any task is expected to approach, because one board task can legitimately hold a "
    "coding agent for a long time. Lower it when a board's tasks are small and a stuck agent "
    "should surface quickly instead of blocking the whole run. The timeout applies per "
    "attempt, so each retry gets the full allowance again."
)
_IDEMPOTENCY_KEY_HELP = (
    "A caller-supplied key that makes the paid admission for this run replay-safe. Leave it "
    "unset and the CLI generates a fresh key, which is correct for every new board. Reuse the "
    "key from an earlier invocation only to recover an admission whose response you never "
    "saw, so the wallet is not charged a second time for the same run. Reusing a key does not "
    "resume or deduplicate the board itself: use --from for that, and every model call is "
    "billed to your own OpenAI account again."
)
_CHECKPOINT_HELP = (
    "Whether every finished step is saved under the checkpoint root as it completes, so a "
    "later invocation can resume, repair, replay, or fork without re-running paid turns. Each "
    "step stores its prompt, bounded summary, thread ID, and reported token count in one "
    "atomic JSON file, plus a manifest holding the board and its context settings. "
    "Checkpointing is on by default and costs nothing beyond local disk. Pass --no-checkpoint "
    "for a run that must leave no trace, noting that every resume and reporting option then "
    "has nothing to read and is rejected."
)
_CHECKPOINT_ROOT_HELP = (
    "The directory that holds boards, one subdirectory per board id. It defaults to "
    ".vidbyte/task-board under the current working directory, which keeps a project's boards "
    "with the project. Point it somewhere explicit, such as ./runs/exp-a, to isolate one "
    "experiment so several boards can run side by side without ever colliding. The path is "
    "resolved to an absolute directory and returned in the result, so a later command can "
    "address the board from any working directory. It is created on the first checkpoint write."
)
_CHECKPOINT_ID_HELP = (
    "The directory name identifying one board inside the checkpoint root. Leave it unset on a "
    "run and the CLI derives twelve hex characters from a hash of the task list, so re-running "
    "the identical board naturally finds its own prior steps. Set it explicitly to keep "
    "several runs of an evolving board apart, or to address a specific stored board when "
    "resuming, forking, or inspecting one. The value holds 1 to 64 letters, digits, dots, "
    "underscores, or hyphens, and on a run it requires checkpointing to stay enabled."
)
_CHECKPOINT_MODE_HELP = (
    "What happens, beyond the durable save, each time a step is checkpointed. save-only, the "
    "default, writes the step file silently and is what an unattended overnight board wants. "
    "stream additionally emits one record per step on the results stream, so a parent agent "
    "watching with --format jsonl sees each summary as it lands instead of waiting for the "
    "board to end. export additionally appends one line per step to a single append-only "
    "file, which is what an outside forking or indexing tool should tail. The mode changes "
    "visibility only: the same step files are written in all three."
)
_EXPORT_FILE_HELP = (
    "Where --checkpoint-mode export appends its one-line-per-step log. Leave it unset and the "
    "log is progress.jsonl inside the board directory, which keeps it with the board it "
    "describes. Point it somewhere shared when several boards should feed one downstream "
    "index. Because the file grows in completion order and is only ever appended to, a "
    "forking tool can read the prefix it needs without scanning or sorting a directory. It is "
    "ignored unless --checkpoint-mode is export."
)
_REPORT_FILE_HELP = (
    "Write a Markdown report of the board's stored history to this path when the run ends. "
    "The report opens with the totals — tasks, completed, failed, pending, tokens, estimated "
    "spend — and then gives one section per stored step with its task and summary. Because "
    "the format is stable prose rather than JSON, it can be attached to a ticket or handed to "
    "someone who will never open a checkpoint file. It is written from the same stored chain "
    "that status reads, so the document and the machine record can never disagree."
)
_ON_CHECKPOINT_HELP = (
    "A shell command to run after each successful checkpoint save, with BOARD_DIR, BOARD_ID, "
    "STEP_FILE, STEP_INDEX, and STEP_STATUS set in its environment. Use it to trigger an "
    "embedding job, a backup, or a notification without waiting for these to become CLI "
    "features. The hook is an observer and never a gate: it runs with a sixty-second timeout, "
    "and a failure is reported on stderr while the board keeps its progress and continues. It "
    "runs your own shell, so treat it exactly as seriously as any other command you would type."
)
_FROM_HELP = (
    "Resume a previously checkpointed board starting at step INDEX, skipping paid turns for "
    "every earlier step. Steps before INDEX load from disk and seed the handoff window exactly "
    "as if they had just run, so step 70 sees the entries for steps 60 through 69 from "
    "storage. Only INDEX through the end of the board execute, and nothing before it is "
    "rewritten. If no task source is given, the board's own stored task list is reused, which "
    "is what makes the returned resume command paste-able. Resuming still buys one fresh flat "
    "admission, and the stored board and settings must match or the run is rejected before pay."
)
_REPLAY_TASK_HELP = (
    "Re-run exactly one board step for debugging, rebuilding its prompt byte-identically from "
    "the task text plus the stored entries its window would have held. Only the addressed step "
    "executes, in a fresh agent with the normal retry policy, and only its checkpoint file is "
    "overwritten. The rest of the board is untouched, which is what makes replay safe to "
    "repeat while chasing a flaky step. It requires checkpoints from a prior run of the same "
    "board and cannot be combined with --from."
)
_PRINT_PROMPT_HELP = (
    "Rebuild the prompt --replay-task would send and return it without starting any agent. No "
    "admission is bought, no model turn runs, and nothing on disk changes, so previewing is "
    "free and instant. Use it to confirm the window really holds the summaries you expect "
    "before spending on a turn that would only prove it did not. It requires --replay-task and "
    "an existing checkpointed board, and it is the only run invocation that never pays."
)
_STOP_AFTER_HELP = (
    "Stop this invocation after N newly executed steps and return control to the caller. The "
    "board is not abandoned: every finished step is checkpointed as usual and the result "
    "carries the resume command that continues from the next index. Use it to run a long board "
    "in reviewable slices, so a parent agent can inspect ten steps, adjust, and then run the "
    "next ten. Leaving it unset runs to the end of the board, which is the existing behavior."
)
_RETRY_FAILED_ONLY_HELP = (
    "Re-run only the steps a previous run recorded as failed, instead of everything after the "
    "resume point. A board with 97 successes and 3 failures then costs three model turns "
    "rather than paying again for work that already landed. Successful steps keep their stored "
    "results and still seed the handoff window, so a repaired step sees the same context it "
    "would have seen originally. It requires an existing checkpointed board, and --from acts "
    "as a floor on which failures are eligible."
)
_MAX_TOKENS_HELP = (
    "Halt the board once the reported provider tokens for this invocation reach this many. "
    "The check happens between steps, so at most one step can overshoot the limit rather than "
    "a runaway board burning through a budget unnoticed. Steps whose provider reported no "
    "usage count as zero here, because an unknown token count is never guessed at. When the "
    "limit stops a board the result says so and carries the resume command, so the run can "
    "continue after you approve more spend."
)
_MAX_COST_HELP = (
    "Halt the board once the estimated spend for this invocation reaches this many US dollars. "
    "The estimate is the reported token total priced at --usd-per-million-tokens, so it is only "
    "as good as that rate and only counts turns whose usage the provider actually reported. "
    "Like --max-tokens the check runs between steps, so one step may overshoot. When the limit "
    "stops a board the result says so and returns the resume command to continue after approval."
)
_USD_PER_MILLION_HELP = (
    "The rate used to turn reported tokens into the estimated spend stored on every step and "
    "returned with the board. It defaults to ten dollars per million tokens, which is a "
    "placeholder rather than a quote for any specific model. Set it to your model's real "
    "blended rate whenever you intend to rely on --max-cost, because the guard is only as "
    "accurate as this number. It affects estimates and budget checks only and never changes "
    "what anyone actually bills you."
)
_STATUS_ID_HELP = (
    "The board id to read, as listed by the list subcommand and shown in every run result. It "
    "names one directory inside the checkpoint root, so it is the whole address of a board "
    "together with --checkpoint-root. There is no default, because reading the wrong board "
    "silently is worse than being asked which one you meant. Pass the same id back to "
    "show-step, fork, or a resuming run to keep working on that board."
)
_INDEX_HELP = (
    "Which board step to read, given as its zero-based board position. The step must already "
    "have a checkpoint file, so run status first if you are unsure which indices this board "
    "stored. There is no default because there is no sensible step to guess at. The response "
    "carries that step's whole record, including the exact prompt it received."
)
_FORK_AT_HELP = (
    "How many leading steps to copy into the new board, so --at 70 copies steps 0 through 69. "
    "The new board then continues from step 70 while the original keeps its own steps 70 "
    "onward untouched, which is what makes two endings comparable. Every step below this index "
    "must exist on disk, and the fork fails naming the first gap rather than copying a partial "
    "prefix. Choose the index where the two experiments should diverge."
)
_FORK_INTO_HELP = (
    "The board id the copied prefix is written to, inside the same checkpoint root. It has to "
    "be a new name, because writing a fork over an existing board would destroy the history "
    "that board already holds. Choose something you will recognize later, such as exp-b, since "
    "this is the id you will pass to resume, status, and show-step from now on. The value "
    "holds 1 to 64 letters, digits, dots, underscores, or hyphens."
)
_EXPORT_TO_HELP = (
    "The file the board's task list is written to. A .md destination gets one level-two "
    "section per task, and a .json destination gets a flat array of task strings; both reload "
    "through --task-list to exactly the board that was exported. Parent directories are "
    "created as needed and an existing file is overwritten, so point it somewhere deliberate. "
    "There is no default, because writing a board to a guessed path is not recoverable."
)


class TaskBoardCommand:
    """Keeps board validation and provider credentials ahead of paid admission."""

    def register(self, parent: click.Group) -> None:
        # Attaches the task-board group: one paid run verb plus the free, offline read verbs.
        @parent.group(name="task-board", help=_GROUP_HELP)
        def _board() -> None:
            pass

        self._register_run(_board)
        self._register_list(_board)
        self._register_status(_board)
        self._register_show_step(_board)
        self._register_fork(_board)
        self._register_export_tasks(_board)

    def _register_run(self, board: click.Group) -> None:
        # Attaches run with its board source, context, agent, checkpoint, and budget options.
        @board.command(name="run", help=_COMMAND_HELP)
        @click.argument("tasks", nargs=-1)
        @click.option(
            "--task-file",
            "task_files",
            multiple=True,
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            help=_TASK_FILE_HELP,
        )
        @click.option(
            "--task-list",
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            default=None,
            help=_TASK_LIST_HELP,
        )
        @click.option(
            "--host",
            type=click.Choice(("auto", "codex")),
            default="codex",
            show_default=True,
            help=_HOST_HELP,
        )
        @click.option(
            "--window", type=click.IntRange(0, 25), default=10, show_default=True, help=_WINDOW_HELP
        )
        @click.option(
            "--context-mode",
            type=click.Choice(("windowed-summaries", "isolated")),
            default="windowed-summaries",
            show_default=True,
            help=_CONTEXT_MODE_HELP,
        )
        @click.option(
            "--handoff",
            type=click.Choice(("summary", "task-and-summary", "full-result")),
            default="summary",
            show_default=True,
            help=_HANDOFF_HELP,
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
        @click.option("--model", default="", help=_MODEL_HELP)
        @click.option(
            "--sandbox",
            type=click.Choice(("read-only", "workspace-write", "full-access")),
            default="workspace-write",
            show_default=True,
            help=_SANDBOX_HELP,
        )
        @click.option(
            "--reasoning-effort",
            type=click.Choice(("", "minimal", "low", "medium", "high", "xhigh")),
            default="",
            help=_REASONING_EFFORT_HELP,
        )
        @click.option(
            "--turn-timeout",
            type=click.IntRange(60, 5 * 24 * 60 * 60),
            default=5 * 24 * 60 * 60,
            show_default=True,
            help=_TURN_TIMEOUT_HELP,
        )
        @click.option("--idempotency-key", "key", default=None, help=_IDEMPOTENCY_KEY_HELP)
        @click.option(
            "--checkpoint/--no-checkpoint", default=True, show_default=True, help=_CHECKPOINT_HELP
        )
        @click.option(
            "--checkpoint-root",
            type=click.Path(file_okay=False, path_type=Path),
            default=_DEFAULT_CHECKPOINT_ROOT,
            show_default=True,
            help=_CHECKPOINT_ROOT_HELP,
        )
        @click.option("--checkpoint-id", default=None, help=_CHECKPOINT_ID_HELP)
        @click.option(
            "--checkpoint-mode",
            type=click.Choice(("save-only", "stream", "export")),
            default="save-only",
            show_default=True,
            help=_CHECKPOINT_MODE_HELP,
        )
        @click.option(
            "--export-file",
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            help=_EXPORT_FILE_HELP,
        )
        @click.option(
            "--report-file",
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            help=_REPORT_FILE_HELP,
        )
        @click.option("--on-checkpoint", default="", help=_ON_CHECKPOINT_HELP)
        @click.option(
            "--from",
            "--resume-from",
            "start_from",
            type=click.IntRange(0),
            default=None,
            help=_FROM_HELP,
        )
        @click.option("--replay-task", type=click.IntRange(0), default=None, help=_REPLAY_TASK_HELP)
        @click.option("--print-prompt", is_flag=True, default=False, help=_PRINT_PROMPT_HELP)
        @click.option("--stop-after", type=click.IntRange(1), default=None, help=_STOP_AFTER_HELP)
        @click.option(
            "--retry-failed-only", is_flag=True, default=False, help=_RETRY_FAILED_ONLY_HELP
        )
        @click.option("--max-tokens", type=click.IntRange(1), default=None, help=_MAX_TOKENS_HELP)
        @click.option(
            "--max-cost",
            type=click.FloatRange(min=0, min_open=True),
            default=None,
            help=_MAX_COST_HELP,
        )
        @click.option(
            "--usd-per-million-tokens",
            type=click.FloatRange(0),
            default=10.0,
            show_default=True,
            help=_USD_PER_MILLION_HELP,
        )
        @click.pass_obj
        def _run(ctx: Context, /, tasks: tuple[str, ...], **options: object) -> None:
            # Groups the parsed values into the two frozen contracts the runner consumes, so
            # the execution method takes bounded objects rather than thirty positional flags.
            self.execute(ctx, tasks, options)

    def _register_list(self, board: click.Group) -> None:
        # Attaches the offline board index over one checkpoint root.
        @board.command(name="list", help=_LIST_HELP)
        @click.option(
            "--checkpoint-root",
            type=click.Path(file_okay=False, path_type=Path),
            default=_DEFAULT_CHECKPOINT_ROOT,
            show_default=True,
            help=_CHECKPOINT_ROOT_HELP,
        )
        @click.pass_obj
        def _list(ctx: Context, checkpoint_root: Path) -> None:
            self.execute_list(ctx, checkpoint_root)

    def _register_status(self, board: click.Group) -> None:
        # Attaches the offline per-board progress report.
        @board.command(name="status", help=_STATUS_HELP)
        @click.option(
            "--checkpoint-root",
            type=click.Path(file_okay=False, path_type=Path),
            default=_DEFAULT_CHECKPOINT_ROOT,
            show_default=True,
            help=_CHECKPOINT_ROOT_HELP,
        )
        @click.option("--checkpoint-id", required=True, help=_STATUS_ID_HELP)
        @click.option(
            "--report-file",
            type=click.Path(dir_okay=False, path_type=Path),
            default=None,
            help=_REPORT_FILE_HELP,
        )
        @click.pass_obj
        def _status(
            ctx: Context, checkpoint_root: Path, checkpoint_id: str, report_file: Path | None
        ) -> None:
            self.execute_status(ctx, checkpoint_root, checkpoint_id, report_file)

    def _register_show_step(self, board: click.Group) -> None:
        # Attaches single-step inspection so debugging costs one call, not several file reads.
        @board.command(name="show-step", help=_SHOW_STEP_HELP)
        @click.option(
            "--checkpoint-root",
            type=click.Path(file_okay=False, path_type=Path),
            default=_DEFAULT_CHECKPOINT_ROOT,
            show_default=True,
            help=_CHECKPOINT_ROOT_HELP,
        )
        @click.option("--checkpoint-id", required=True, help=_STATUS_ID_HELP)
        @click.option("--index", type=click.IntRange(0), required=True, help=_INDEX_HELP)
        @click.pass_obj
        def _show_step(ctx: Context, checkpoint_root: Path, checkpoint_id: str, index: int) -> None:
            self.execute_show_step(ctx, checkpoint_root, checkpoint_id, index)

    def _register_fork(self, board: click.Group) -> None:
        # Attaches prefix copying, which branches a board without touching the original.
        @board.command(name="fork", help=_FORK_HELP)
        @click.option(
            "--checkpoint-root",
            type=click.Path(file_okay=False, path_type=Path),
            default=_DEFAULT_CHECKPOINT_ROOT,
            show_default=True,
            help=_CHECKPOINT_ROOT_HELP,
        )
        @click.option("--checkpoint-id", required=True, help=_STATUS_ID_HELP)
        @click.option("--at", "at_index", type=click.IntRange(0), required=True, help=_FORK_AT_HELP)
        @click.option("--into", required=True, help=_FORK_INTO_HELP)
        @click.pass_obj
        def _fork(
            ctx: Context, checkpoint_root: Path, checkpoint_id: str, at_index: int, into: str
        ) -> None:
            self.execute_fork(ctx, checkpoint_root, checkpoint_id, at_index, into)

    def _register_export_tasks(self, board: click.Group) -> None:
        # Attaches task-list export, the inverse of --task-list import.
        @board.command(name="export-tasks", help=_EXPORT_TASKS_HELP)
        @click.option(
            "--checkpoint-root",
            type=click.Path(file_okay=False, path_type=Path),
            default=_DEFAULT_CHECKPOINT_ROOT,
            show_default=True,
            help=_CHECKPOINT_ROOT_HELP,
        )
        @click.option("--checkpoint-id", required=True, help=_STATUS_ID_HELP)
        @click.option(
            "--to",
            "destination",
            type=click.Path(dir_okay=False, path_type=Path),
            required=True,
            help=_EXPORT_TO_HELP,
        )
        @click.pass_obj
        def _export(
            ctx: Context, checkpoint_root: Path, checkpoint_id: str, destination: Path
        ) -> None:
            self.execute_export_tasks(ctx, checkpoint_root, checkpoint_id, destination)

    def execute(
        self, context: Context, tasks: tuple[str, ...], options: Mapping[str, object]
    ) -> None:
        # Everything before ADMISSION is free, so every rejection a caller can cause happens
        # before the wallet is touched, and execution happens only after the grant is verified.
        parsed = TaskBoardOptions(options)
        progress = context.output().diagnostic
        progress(Progress.PREPARING)
        # The key is validated first because an invalid one would otherwise surface only after
        # the board has been read from disk and a host has been resolved.
        key = self._idempotency_key(parsed.key)
        # Checkpoint storage is resolved before the board is read, because a resume with no
        # task source of its own gets its board back out of the stored manifest.
        checkpointer = self._checkpointer(parsed)
        # Resolving the board is the one step that reads caller files; it fails closed on a
        # mixed, empty, non-Markdown, or unreadable source.
        stored = checkpointer if parsed.resumes else None
        board = self._board_tasks(tasks, parsed.task_files, parsed.task_list, stored)
        settings = self._settings(board, parsed)
        controls = parsed.controls()
        checkpointer = self._identified(checkpointer, parsed, board)
        # A prompt preview never starts an agent, so it returns before credentials or payment.
        if parsed.print_prompt:
            self._preview(context, checkpointer, settings, controls)
            return
        # Proving the stored prefix loads before admission is what stops a doomed resume paying.
        self._validate_resume(checkpointer, settings, parsed)
        requested = None if parsed.host == "auto" else RuntimeHost(parsed.host)
        # The plan carries only a board label, never the task text: task content is local and
        # must not travel to the backend with the admission request.
        plan = context.runtime_launch_planner().build_task_board(board, requested, Path.cwd())
        progress(Progress.CREDENTIALS)
        # Building the session imports the SDK and filters the child environment, so a missing
        # SDK or a missing provider key also fails before payment.
        session = self._session(context, checkpointer, controls)
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

    def execute_list(self, context: Context, checkpoint_root: Path) -> None:
        # Offline and free: one row per board directory holding a readable manifest.
        root = checkpoint_root.expanduser().resolve()
        boards = TaskBoardCheckpointer.list_boards(root)
        rows = [
            f"{item.board_id}  {item.completed}/{item.task_count} done, "
            f"{item.failed} failed, {item.pending} pending  {item.board_dir}"
            for item in boards
        ]
        listing = TaskBoardListing(
            checkpoint_root=str(root),
            boards=boards,
            text="\n".join(rows) if rows else f"No checkpointed boards under {root}.",
        )
        context.output().result(
            OutputDocument(kind="runtime.task-board.list", data=listing.model_dump(mode="json")),
            listing.text,
        )

    def execute_status(
        self, context: Context, checkpoint_root: Path, board_id: str, report_file: Path | None
    ) -> None:
        # Offline and free, so an agent can call it between every decision it makes.
        checkpointer = self._read_only(checkpoint_root, board_id)
        chain = checkpointer.chain()
        spend = sum(node.estimated_cost_usd or 0.0 for node in chain.nodes)
        report = None if report_file is None else str(checkpointer.write_report(chain, report_file))
        status = TaskBoardStatusReport(
            board_id=chain.board_id,
            board_dir=chain.board_dir,
            task_count=chain.task_count,
            completed_indices=chain.completed_indices,
            failed_indices=chain.failed_indices,
            pending_indices=chain.pending_indices,
            total_tokens=chain.total_tokens,
            estimated_cost_usd=round(spend, 6),
            parent_board_id=chain.parent_board_id,
            report_file=report,
            resume_command=self._resume_command(checkpointer, chain),
            text=(
                f"{chain.board_id}: {len(chain.completed_indices)} completed, "
                f"{len(chain.failed_indices)} failed, {len(chain.pending_indices)} pending "
                f"of {chain.task_count} in {chain.board_dir}"
            ),
        )
        context.output().result(
            OutputDocument(kind="runtime.task-board.status", data=status.model_dump(mode="json")),
            status.text,
        )

    def execute_show_step(
        self, context: Context, checkpoint_root: Path, board_id: str, index: int
    ) -> None:
        # Returns the whole stored record, so a caller never has to open a checkpoint file.
        checkpointer = self._read_only(checkpoint_root, board_id)
        record = checkpointer.read_step(index)
        chain = checkpointer.chain()
        detail = TaskBoardStepDetail(
            board_id=checkpointer.board_id,
            board_dir=str(checkpointer.directory),
            step_file=str(checkpointer.step_file(index)),
            step=record,
            ancestors=tuple(node.index for node in chain.ancestors_of(index)),
            text=f"[{record.index}] {record.status}: {record.summary}",
        )
        context.output().result(
            OutputDocument(kind="runtime.task-board.step", data=detail.model_dump(mode="json")),
            detail.text,
        )

    def execute_fork(
        self, context: Context, checkpoint_root: Path, board_id: str, at_index: int, into: str
    ) -> None:
        # Copies a prefix into a new board; the source board is only ever read.
        source = self._read_only(checkpoint_root, board_id)
        self._require_board_id(into)
        root = checkpoint_root.expanduser().resolve()
        target = TaskBoardCheckpointer(root, into)
        if target.directory.exists():
            raise click.BadParameter(f"Board {into} already exists under {root}.")
        copied = source.fork_into(target, at_index)
        fork = TaskBoardForkResult(
            board_id=into,
            board_dir=str(target.directory),
            parent_board_id=source.board_id,
            forked_at_index=at_index,
            copied_steps=copied,
            resume_command=target.resume_command(at_index),
            text=f"Forked {source.board_id} at step {at_index} into {target.directory}",
        )
        context.output().result(
            OutputDocument(kind="runtime.task-board.fork", data=fork.model_dump(mode="json")),
            fork.text,
        )

    def execute_export_tasks(
        self, context: Context, checkpoint_root: Path, board_id: str, destination: Path
    ) -> None:
        # Writes the stored board back out in a shape --task-list reads back identically.
        checkpointer = self._read_only(checkpoint_root, board_id)
        board = checkpointer.stored_tasks()
        written = TaskBoardFileStore(Path.cwd()).write_task_list(
            destination.expanduser().resolve(), board
        )
        export = TaskBoardTaskExport(
            board_id=checkpointer.board_id,
            path=str(written),
            task_count=len(board),
            text=f"Wrote {len(board)} tasks to {written}",
        )
        context.output().result(
            OutputDocument(kind="runtime.task-board.tasks", data=export.model_dump(mode="json")),
            export.text,
        )

    def _preview(
        self,
        context: Context,
        checkpointer: TaskBoardCheckpointer | None,
        settings: TaskBoardSettings,
        controls: TaskBoardRunControls,
    ) -> None:
        # The one run invocation that never pays: it rebuilds a prompt and returns it.
        if checkpointer is None or controls.replay_index is None:
            raise click.BadParameter("--print-prompt requires --replay-task and checkpointing.")
        session = TaskBoardCodexSession({}, context.output().diagnostic)
        session.with_checkpoints(checkpointer, controls)
        prompt = session.preview_prompt(settings, controls.replay_index)
        preview = TaskBoardPromptPreview(
            board_id=checkpointer.board_id,
            board_dir=str(checkpointer.directory),
            index=controls.replay_index,
            prompt=prompt,
            text=prompt,
        )
        context.output().result(
            OutputDocument(kind="runtime.task-board.prompt", data=preview.model_dump(mode="json")),
            preview.text,
        )

    def _read_only(self, checkpoint_root: Path, board_id: str) -> TaskBoardCheckpointer:
        # Every offline verb addresses a board the same way, and proves it exists before use.
        self._require_board_id(board_id)
        checkpointer = TaskBoardCheckpointer(checkpoint_root.expanduser().resolve(), board_id)
        checkpointer.read_manifest()
        return checkpointer

    def _require_board_id(self, board_id: str) -> None:
        # One character class for every board id, so a board can never escape its own root.
        if re.fullmatch(_BOARD_ID_PATTERN, board_id) is None:
            raise click.BadParameter("Use 1–64 letters, digits, dots, underscores or hyphens.")

    def _resume_command(
        self, checkpointer: TaskBoardCheckpointer, chain: TaskBoardCheckpointChain
    ) -> str:
        # Points at the first unfinished step, or at repair when only failures remain, so the
        # command a caller pastes back never re-pays for steps that already completed.
        if chain.failed_indices:
            return checkpointer.resume_command(0, repair=True)
        pending = chain.pending_indices
        return checkpointer.resume_command(pending[0] if pending else chain.task_count)

    def _board_tasks(
        self,
        tasks: tuple[str, ...],
        task_files: tuple[Path, ...],
        task_list: Path | None = None,
        stored: TaskBoardCheckpointer | None = None,
    ) -> tuple[str, ...]:
        # A board comes from exactly one source: literal task strings, whole Markdown files one
        # task each, one task-list file, or the list a stored board recorded. Accepting two at
        # once would leave the board's order ambiguous.
        store = TaskBoardFileStore(Path.cwd())
        literals = tuple(item for item in (task.strip() for task in tasks) if item)
        if sum((bool(literals), bool(task_files), task_list is not None)) > 1:
            raise TaskBoardInputInvalid()
        if literals:
            return literals
        if task_files:
            return tuple(store.read_task_file(path) for path in task_files)
        if task_list is not None:
            return store.read_task_list(task_list)
        if stored is not None:
            return stored.stored_tasks()
        raise TaskBoardInputInvalid()

    def _settings(self, board: tuple[str, ...], parsed: TaskBoardOptions) -> TaskBoardSettings:
        # Constructs frozen board settings with validated context, handoff, and agent behavior.
        return TaskBoardSettings(
            tasks=board,
            window=parsed.window,
            context_mode=TaskBoardContextMode(parsed.context_mode),
            handoff_mode=TaskBoardHandoffMode(parsed.handoff),
            summary_mode=TaskBoardSummaryMode(parsed.summary_mode),
            summary_max_chars=parsed.summary_max_chars,
            stop_on_error=parsed.stop_on_error,
            max_retries_per_task=parsed.retries_per_task,
            agent=parsed.agent(),
        )

    def _checkpointer(self, parsed: TaskBoardOptions) -> TaskBoardCheckpointer | None:
        # Derives the board directory without touching disk; resume flags require storage. The
        # id may still be unknown here, because a hashed id needs the board that is read next.
        if parsed.start_from is not None and parsed.replay_task is not None:
            raise click.BadParameter("--from and --replay-task cannot be combined.")
        if not parsed.checkpoint:
            if parsed.resumes or parsed.checkpoint_id is not None or parsed.report_file:
                raise click.BadParameter("Resume options require checkpointing to stay enabled.")
            return None
        if parsed.checkpoint_id is None:
            return None
        self._require_board_id(parsed.checkpoint_id)
        return TaskBoardCheckpointer(parsed.root(), parsed.checkpoint_id)

    def _identified(
        self,
        checkpointer: TaskBoardCheckpointer | None,
        parsed: TaskBoardOptions,
        board: tuple[str, ...],
    ) -> TaskBoardCheckpointer | None:
        # An unnamed board is addressed by the hash of its task list, which is only knowable
        # once the board itself has been resolved from whichever source supplied it.
        if checkpointer is not None or not parsed.checkpoint:
            return checkpointer
        return TaskBoardCheckpointer(parsed.root(), TaskBoardCheckpointer.board_id_for(board))

    def _validate_resume(
        self,
        checkpointer: TaskBoardCheckpointer | None,
        settings: TaskBoardSettings,
        parsed: TaskBoardOptions,
    ) -> None:
        # Proves the stored prefix loads before admission so a doomed resume never pays.
        if checkpointer is None:
            return
        board_size = len(settings.tasks)
        if parsed.start_from is not None and parsed.start_from > board_size:
            raise click.BadParameter(f"--from {parsed.start_from} is past this board.")
        if parsed.replay_task is not None and parsed.replay_task >= board_size:
            raise click.BadParameter(f"--replay-task {parsed.replay_task} is past this board.")
        if parsed.retry_failed_only:
            checkpointer.validate_manifest(settings)
            return
        if parsed.start_from:
            checkpointer.validate_manifest(settings)
            checkpointer.load_prefix(parsed.start_from)
        elif parsed.replay_task is not None:
            checkpointer.validate_manifest(settings)
            checkpointer.load_prefix(parsed.replay_task)

    def _idempotency_key(self, key: str | None) -> str:
        # Validates the replay-safe admission key before any local planning.
        candidate = key or str(uuid4())
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", candidate) is None:
            raise click.BadParameter(
                "Use 8–128 letters, digits, dots, underscores, colons or hyphens."
            )
        return candidate

    def _session(
        self,
        context: Context,
        checkpointer: TaskBoardCheckpointer | None,
        controls: TaskBoardRunControls,
    ) -> TaskBoardCodexSession:
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
        session = TaskBoardCodexSession(
            environment, context.output().diagnostic, self._streamer(context)
        )
        if checkpointer is not None:
            session.with_checkpoints(checkpointer, controls)
        return session

    def _streamer(self, context: Context) -> Callable[[TaskBoardCheckpoint], None]:
        # Streamed steps are transitions, not the final result, so a --json consumer still
        # sees exactly one document while a --jsonl consumer sees each step as it lands.
        def emit(record: TaskBoardCheckpoint) -> None:
            context.output().transition(
                OutputDocument(kind="runtime.task-board.step", data=record.model_dump(mode="json")),
                f"[{record.index}] {record.status}: {record.summary}",
            )

        return emit


class TaskBoardOptions:
    """The parsed run invocation: board sources, board settings, and this run's controls."""

    def __init__(self, options: Mapping[str, object]) -> None:
        # Click has already type-checked every value, so this only names them and fixes types.
        self.task_files = self._paths(options["task_files"])
        self.task_list = self._path(options["task_list"])
        self.host = str(options["host"])
        self.window = int(str(options["window"]))
        self.context_mode = str(options["context_mode"])
        self.handoff = str(options["handoff"])
        self.summary_mode = str(options["summary_mode"])
        self.summary_max_chars = int(str(options["summary_max_chars"]))
        self.stop_on_error = bool(options["stop_on_error"])
        self.retries_per_task = int(str(options["retries_per_task"]))
        self.model = str(options["model"])
        self.sandbox = str(options["sandbox"])
        self.reasoning_effort = str(options["reasoning_effort"])
        self.turn_timeout = int(str(options["turn_timeout"]))
        self.key = self._text(options["key"])
        self.checkpoint = bool(options["checkpoint"])
        self.checkpoint_root = self._paths((options["checkpoint_root"],))[0]
        self.checkpoint_id = self._text(options["checkpoint_id"])
        self.checkpoint_mode = str(options["checkpoint_mode"])
        self.export_file = self._path(options["export_file"])
        self.report_file = self._path(options["report_file"])
        self.on_checkpoint = str(options["on_checkpoint"])
        self.start_from = self._number(options["start_from"])
        self.replay_task = self._number(options["replay_task"])
        self.print_prompt = bool(options["print_prompt"])
        self.stop_after = self._number(options["stop_after"])
        self.retry_failed_only = bool(options["retry_failed_only"])
        self.max_tokens = self._number(options["max_tokens"])
        self.max_cost = self._decimal(options["max_cost"])
        self.usd_per_million_tokens = float(str(options["usd_per_million_tokens"]))

    @property
    def resumes(self) -> bool:
        # Whether this invocation reads a stored board rather than starting a fresh one.
        return self.start_from is not None or self.replay_task is not None or self.retry_failed_only

    def root(self) -> Path:
        # Absolute from here on, which is what makes a returned board directory portable.
        return self.checkpoint_root.expanduser().resolve()

    def agent(self) -> TaskBoardAgentSettings:
        # The Codex configuration every iteration of this board is constructed with.
        return TaskBoardAgentSettings(
            model=self.model,
            sandbox=TaskBoardSandbox(self.sandbox),
            reasoning_effort=TaskBoardReasoningEffort(self.reasoning_effort),
            turn_timeout_seconds=self.turn_timeout,
        )

    def controls(self) -> TaskBoardRunControls:
        # Everything that varies per invocation rather than per board, kept out of the board
        # fingerprint so a resume with a different budget is not mistaken for a different board.
        return TaskBoardRunControls(
            checkpoint_mode=TaskBoardCheckpointMode(self.checkpoint_mode),
            export_file="" if self.export_file is None else str(self.export_file),
            report_file="" if self.report_file is None else str(self.report_file),
            on_checkpoint=self.on_checkpoint,
            start_from=self.start_from or 0,
            replay_index=self.replay_task,
            stop_after=self.stop_after,
            retry_failed_only=self.retry_failed_only,
            max_tokens=self.max_tokens,
            max_cost_usd=self.max_cost,
            usd_per_million_tokens=self.usd_per_million_tokens,
        )

    @staticmethod
    def _paths(value: object) -> tuple[Path, ...]:
        return (
            tuple(item for item in value if isinstance(item, Path))
            if isinstance(value, tuple)
            else ()
        )

    @staticmethod
    def _path(value: object) -> Path | None:
        return value if isinstance(value, Path) else None

    @staticmethod
    def _text(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _number(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _decimal(value: object) -> float | None:
        return (
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )
