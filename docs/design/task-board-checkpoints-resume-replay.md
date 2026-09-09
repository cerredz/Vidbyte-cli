# Design Doc — Task Board Checkpoints, Resume, and Replay

## 1. Overview

A crash on task 70 of 100 currently means starting over from task 0. This doc adds
per-step checkpointing to the `runtime.task-board@1` CLI primitive: after each task
finishes, the session durably saves that step's prompt, summary, thread ID, token
count, and estimated cost to disk. `task-board resume --from 70` then continues the
same board from disk without re-running tasks 0–69, and `replay --task 42` re-runs
one step with the identical prompt for debugging.

## 2. Goals / Non-Goals

### Goals

- Persist one checkpoint file per completed step, written atomically right after the
  step finishes, containing prompt, summary, thread ID, tokens, and estimated cost.
- Add `resume` semantics (`--from INDEX`) that reload prior steps from disk, seed the
  summary window from them, and execute only steps `INDEX..N-1`.
- Add `replay` semantics (`--replay-task INDEX`) that rebuild the exact prompt for one
  step (same task text, same windowed summaries) and run only that step in a fresh
  `CodexHarnessAgent`.
- Keep checkpoints offline, local-only, and free: no backend route, no admission change.

### Non-Goals

- N/A — Branching or forking checkpoint history is out of scope; resume always continues
  the single linear prefix stored on disk.
- N/A — Resuming a board whose task list changed is out of scope; a board-hash check
  rejects mismatched boards instead of merging them.
- N/A — Checkpoint encryption or redaction is out of scope; prompts already live in
  local `--task-file` inputs and stay under the same trust boundary.

## 3. Background

`TaskBoardCodexSession._run` (`src/vidbyte_cli/lib/runtime_primitives/task_board.py`)
loops `settings.tasks` in order, builds one fresh `CodexHarnessAgent` per task via
`_build_agent`, sends `CodexRunInput.text(prompt)`, and validates the reply through
`_completed_text` / `_thread_id`. Summaries accumulate in a local `list[str]` that dies
with the process — hence a crash loses everything.

`CodexHarnessAgent.arun` returns an `AgentMessage` whose `.codex` field is a
`CodexMessageData` carrying `thread_id`, `status`, `final_response`, `usage`
(`CodexUsage` with `input_tokens` / `output_tokens` / `total_tokens`), and
`usage_available`. Token counts are therefore readable at the exact point the session
already validates completion, with no transport change.

Field-guide constraints applied:
`field-guide/vidbyte-cli/runtime-execution.md` (verify-grant-in-command-before-runner,
runner takes SDK plus grant and holds no endpoints),
`field-guide/vidbyte-cli/typed-failures.md` (no standalone functions; new failure
shapes are `CliError` subclasses), `field-guide/vidbyte-cli/implementation-restraint.md`
(3–6 line module docstring, `#` comments on invariants only, no templated headers).

AGENTS.md notes: `vidbyte-cli/AGENTS.md` — stdout is results-only, diagnostics on
stderr; thin transport layer over the SDK.

## 4. Requirements

### Functional

- R1: Every completed or failed step writes `.vidbyte/task-board/<board-id>/step-<i>.json`
  under the invocation cwd before the next step starts, via atomic write-then-rename.
  Record fields: `index`, `task`, `prompt`, `summary`, `status`, `thread_id`,
  `total_tokens` (nullable), `estimated_cost_usd` (nullable).
- R2: `<board-id>` defaults to `sha1` of the joined task list (12 hex chars); overridable
  with `--checkpoint-id`. A `board.json` manifest in the same directory stores the task
  list hash, task count, and settings fingerprint.
- R3: `--from INDEX` resumes: steps `0..INDEX-1` load from disk (missing file is a
  hard failure, never silent re-execution), their summaries seed the window, and only
  `INDEX..N-1` execute. `INDEX=0` is identical to a fresh run.
- R4: `--replay-task INDEX` replays: rebuilds the exact prompt for step INDEX from the
  board plus checkpointed summaries `max(0,INDEX-window)..INDEX-1`, runs it once in a
  fresh agent (retries still apply), and overwrites only `step-INDEX.json`.
- R5: Resume validates the manifest: task count, per-task text, window, context mode,
  and summary settings must match the current invocation, else a typed failure naming
  the first mismatch. Re-running with different settings against old checkpoints is
  rejected, not merged.
- R6: Cost/tokens recorded per step come from `reply.codex.usage.total_tokens` when
  `usage_available` is true; otherwise `total_tokens` is null and cost is estimated as
  `len(summary)//4` tokens at the board rate (nullable spend path, see companion
  budgets doc). Checkpointing never fails a step: a write error marks the step with
  `checkpoint: "write-failed"` in stderr diagnostics and continues.

### Non-functional

- Checkpoint write is O(step size), bounded by the existing 8000-char summary cap plus
  prompt text; prompts are bounded by `window * summary_max_chars + MAX_TASK_CHARS`.
- Offline-testable with fakes at the `_turn` boundary, matching `scripts/test-task-board.py`.
- Strict typing (`mypy`), `ruff check`, `ruff format`, `python scripts/run_ci.py` green.

## 5. High-Level Design

A small `TaskBoardCheckpointer` collaborator owns the directory layout, atomic writes,
manifest validation, and step loading. The session calls it at two points: after each
step completes (save), and before the loop starts when `--from` / `--replay-task` is
given (load + validate). Prompt construction is unchanged and therefore replay is
exact by construction: replay calls the same `_build_prompt` with the same summaries.

Execution flow with resume:

1. Parse settings, build plan, verify grant (unchanged gateway order).
2. Checkpointer loads manifest + steps `0..FROM-1`, validates board hash.
3. Session seeds `summaries` / `steps` from loaded records, executes `FROM..N-1`.
4. Each finished step appends its checkpoint file before the next step starts.

## 6. Detailed Design

### 6.1 Checkpointer (`lib/runtime_primitives/task_board_checkpoints.py`, new file)

Class `TaskBoardCheckpointer` with methods (all single-line signatures + 1–2 line
comments per repo style):

- `write_step(record: TaskBoardCheckpoint) -> None` — atomic write via temp file +
  `os.replace`, creating parent dirs as needed.
- `load_prefix(board_id, count) -> tuple[TaskBoardCheckpoint, ...]` — reads
  `step-0..step-(count-1)`, raising `TaskBoardCheckpointMissing` on any gap.
- `validate_manifest(board_id, settings) -> None` — compares stored hash/count/settings
  fingerprint, raising `TaskBoardCheckpointMismatch` naming the first divergence.
- `board_id_for(tasks) -> str` — `sha1("\x00".join(tasks))[:12]`.

`TaskBoardCheckpoint` is a frozen pydantic model in `types/runtime.py` with the R1
fields plus `admission_id` and `created_at`.

### 6.2 Session changes (`lib/runtime_primitives/task_board.py`)

- `TaskBoardCodexSession.__init__` gains an optional `checkpointer` (default None =
  checkpointing disabled, preserving current behavior for library callers).
- `_run` accepts `start_from: int = 0`; when > 0 it pre-loads steps/summaries from the
  checkpointer before the loop and iterates `range(start_from, len(tasks))`.
- After each step (completed or failed) it calls `write_step` with the prompt used,
  the summary, thread ID, and usage extracted from the reply. Usage extraction is a
  private method `_usage_of(reply) -> int | None` reading `reply.codex.usage`
  guarded by `usage_available`.
- New `replay(plan, settings, admission_id, index) -> TaskBoardResult` builds the
  loaded prefix, rebuilds the prompt via `_build_prompt`, runs `_run_task` once for
  that index, overwrites its checkpoint, and returns a single-step result.

### 6.3 Command changes (`commands/runtime/task_board.py`)

- New options `--checkpoint/--no-checkpoint` (default on when running a board? default
  OFF to preserve current no-disk-side-effect behavior — default ON is the product
  goal; this doc chooses default ON with `--no-checkpoint` opt-out, called out
  explicitly because it is the one behavior change to existing invocations),
  `--checkpoint-id TEXT`, `--from INT` (`--resume-from` alias),
  `--replay-task INT`. `--from` and `--replay-task` are mutually exclusive.
- `--from` / `--replay-task` skip admission re-purchase? No: admission is per
  invocation and still purchased (flat 2¢ covers the run). This is stated in help text
  so callers are not surprised that resume still costs one admission.

### 6.4 Failures (`lib/errors/failures.py`)

- `TaskBoardCheckpointMissing(index, directory)` and
  `TaskBoardCheckpointMismatch(detail)` as `CliError` subclasses with `description`,
  `trace`, `file_path` envelope fields.

## 7. Data Model Changes

- New frozen `TaskBoardCheckpoint` model in `types/runtime.py` (extra=forbid):
  `index`, `task`, `prompt`, `summary`, `status` (`completed` | `failed`),
  `thread_id`, `total_tokens: int | None`, `estimated_cost_usd: float | None`,
  `admission_id`, `created_at: datetime`.
- No backend, ledger, or catalog changes.

## 8. API Changes

- N/A - no backend routes. CLI surface only: `--checkpoint/--no-checkpoint`,
  `--checkpoint-id`, `--from` / `--resume-from`, `--replay-task` on
  `vidbyte_cli runtime task-board`. Each gets the mandatory 4-sentence `--help`.

## 9. File Change Manifest

| File | Change |
|---|---|
| `src/vidbyte_cli/types/runtime.py` | Add `TaskBoardCheckpoint` model |
| `src/vidbyte_cli/lib/runtime_primitives/task_board_checkpoints.py` | NEW: checkpointer class |
| `src/vidbyte_cli/lib/runtime_primitives/task_board.py` | Wire checkpointer, `start_from`, `replay`, usage extraction |
| `src/vidbyte_cli/lib/errors/failures.py` | Add 2 failure classes |
| `src/vidbyte_cli/commands/runtime/task_board.py` | Add 4 options + resume/replay dispatch |
| `src/vidbyte_cli/lib/constants/runtime.py` | Add checkpoint progress copy if needed |
| `scripts/test-task-board-checkpoints.py` | NEW: verification script per §10 |
| `scripts/test_research_only_surface.py` | Only if command names change (they do not) |

Create: 2. Modify: 5. Delete: 0.

## 10. Testing Plan

- [Edge Case] Resume `--from 0` behaves identically to a fresh run (same prompts sent).
- [Edge Case] Single-task board checkpoints and replays correctly.
- [Edge Case] `--from N` where N equals task count returns the stored result with zero
  new turns (empty suffix run).
- [Hidden Failure] Missing `step-3.json` in a `--from 5` resume fails with
  `TaskBoardCheckpointMissing(3)`, never silently re-executes step 3.
- [Hidden Failure] Board text changed since checkpointing fails with
  `TaskBoardCheckpointMismatch` naming the divergence; no step runs.
- [Hidden Failure] Settings fingerprint changed (window 10→5) fails closed before any
  model turn.
- [Silent Failure] Replay prompt equality: captured prompt for step 42 in the original
  run byte-equals the replay prompt (same task, same window summaries).
- [Silent Failure] Window seeding: resumed step 70's prompt contains summaries of steps
  `60..69` loaded from disk, verified by content match.
- [Silent Failure] `usage_available=False` records `total_tokens=None` rather than 0,
  so budgets (companion doc) never treat unknown usage as free.
- [Hidden Assumption] Crash between step completion and checkpoint write loses at most
  one step: simulate by disabling writes for step k, resume recovers steps `< k`.
- [Hidden Assumption] Checkpoint write failure never fails the step: inject unwritable
  directory, step still completes and diagnostics note `write-failed`.
- [Hidden Assumption] `os.replace` atomicity: partial temp files are never read as
  steps (temp suffix excluded from the load glob).

## 11. Dependencies

- None beyond the current `vidbyte-sdk` pin (`CodexMessageData.usage`,
  `usage_available` already exist). No backend deploy needed.

## 12. Rollout

- Ships as additive CLI options; default `--checkpoint` ON changes disk behavior for
  existing users (one small directory per board). Migration: none. Rollback: pass
  `--no-checkpoint` or revert the PR; old invocations without the flags are unaffected
  because resume/replay require explicit flags.

## 13. Open Questions

- Q1: Should `--from` skip admission re-purchase by binding to the original
  `admission_id`? Current answer: no (flat 2¢ per invocation keeps the ledger simple).
- Q2: Retention/GC for `.vidbyte/task-board/` directories? Current answer: none in v1;
  follow-up PR if directories accumulate.

## 14. Alternatives Considered

- Single JSON board file instead of per-step files: rejected — a crash mid-write
  corrupts the whole board file, while per-step atomic files lose at most one step.
- SDK-session-layer persistence (`vidbyte/sessions/`): rejected — that layer checkpoints
  linear agent continuations, while the board owns cross-agent ordering and summaries;
  the board is the correct owner.
- Backend-stored checkpoints: rejected — task content is local-only per
  runtime-primitive policy and must not travel to the backend.
