# Design Doc — Task Board `decompose_tool` (isolated tasks, in-place expansion)

## 1. Overview

Give every task-board agent one tool, `decompose_tool`, that expands an array of subtasks at its own index. Each agent sees only its own task, never sibling tasks or prior summaries. When the agent for task N returns K subtasks, the session replaces the single entry at N with those K entries in order, shifts later tasks right, and executes the children next. A board of 3 tasks where task 1 decomposes into 3 subtasks therefore becomes 5 tasks, with the new items occupying positions 1, 2, and 3.

This change stays CLI-only and reuses the new SDK custom-tool seam for translation plus prompt rendering, but executes decomposition through a deterministic outer loop rather than waiting on native Codex function calling. Admission stays one flat 2c grant; expansion is bounded so one chatty agent cannot turn a small board into a 500-task bill on someone else's model account.

## 2. Goals / Non-Goals

### Goals

- Add `--allow-decompose / --no-allow-decompose` (default off) plus `--max-subtasks` (2–10, default 5) to `runtime task-board`.
- Force isolated per-task prompts whenever decomposition is on, so no agent reads sibling work.
- Parse one deterministic `decompose` envelope per task and splice validated subtasks in place at the parent index.
- Enforce total-board caps (500 tasks, 20k chars each) in Python before any splice, with truncation plus stderr diagnostics.
- Keep depth at exactly one level: subtasks never decompose further in v1.
- Preserve the gateway order, fresh-agent-per-task isolation, retry semantics, and stdout-is-results-only contract.

### Non-Goals

- N/A — Parallel or DAG-aware fan-out; execution stays strictly sequential in board order.
- N/A — Recursive decomposition (children of children); v1 records children as terminal work.
- N/A — Backend changes; no catalog, route, pricing, or ledger change.
- N/A — LLM-based subtask summarization; children are used verbatim after deterministic validation.

## 3. Background

`runtime task-board` (design `docs/design/task-board.md`, shipped in PR #39) models a board as a frozen ordered tuple of task strings. `TaskBoardCommand.execute()` validates locally, builds a label-only `RuntimeLaunchPlan`, constructs frozen `TaskBoardSettings`, filters provider env, prepares `TaskBoardCodexSession`, buys one admission, verifies the grant, then delegates to `RuntimeExecutor.execute_task_board()`. The session loops `enumerate(settings.tasks)` in order; each task gets a fresh `CodexHarnessAgent` with the fixed `task_board_system.md` prompt plus windowed or isolated context through `TaskBoardSummarizer`. Settings, step results, and board results are frozen pydantic models with rich per-field help text, and every new option needs a 4+ sentence `--help` constant to pass lint rule C001.

The pending DAG design (`docs/design/task-board-dag.md`, untracked) adds `--type linear|dag` with topological order and direct-parent context. Decompose maps onto it later as parent-to-child edges, but v1 targets linear boards only and rejects `--allow-decompose` combined with `--type dag` if that flag exists, or documents linear-only behavior.

## 4. Requirements

### Functional

- R1: CLI accepts `--allow-decompose / --no-allow-decompose` (default off) and `--max-subtasks` (`click.IntRange(2, 10)`, default 5).
- R2: When decomposition is on, every agent prompt carries only its own task plus the decompose contract; `--window`, `--summary-mode`, and `--summary-max-chars` are ignored with a stderr note, and `context_mode` behaves as isolated regardless of the flag value.
- R3: The agent returns either normal final text (no decomposition) or final text plus one ```decompose JSON array block naming 2–`max_subtasks` self-contained subtask strings.
- R4: The session validates every candidate: stripped non-empty, 1–20 000 chars, de-duplicated case-insensitively, capped at `max_subtasks`; invalid entries are dropped, never fail the board.
- R5: Valid subtasks replace the parent entry in place: parent at index i becomes children at i..i+K-1; later tasks shift right; the parent step records `status=completed` with summary `Decomposed into K subtasks.` plus its thread id.
- R6: Depth is one: child tasks execute as normal work and their own decompose blocks are ignored with a diagnostic.
- R7: Total board size never exceeds 500 tasks or the per-task char bound; over-cap splices truncate to fit and note the truncation on stderr.
- R8: Retries re-send the identical prompt to a brand-new agent; a retry that succeeds produces exactly one splice.
- R9: `stop_on_error` semantics unchanged; a failed parent never decomposes.
- R10: Result shape unchanged: `TaskBoardResult` with per-step `index`, `task`, `summary`,
  `status`, `thread_id`. Steps stay in execution order; the parent keeps its execution index
  and each child carries the slot it occupies (`parent index` .. `parent index + K - 1`), so
  the parent and its first child share an index by construction and later tasks shift right.

### Non-functional

- Offline-testable parser and splice logic with zero network or SDK imports.
- Strict typing (`mypy`), `ruff check`, `ruff format`, `python lint/run.py` (C001 help depth for two new options), and `python scripts/run_ci.py` green.
- No task text or secrets in errors or progress; diagnostics on stderr only.

## 5. High-Level Design

No backend work. CLI-only change across types, command, session, prompt asset, and errors. The planner, gate, executor, and admission client are untouched; the executor keeps delegating to `session.run()` and the session branches internally on `settings.allow_decompose`.

Flow per invocation with decomposition on:

1. Validate idempotency key, resolve board source, validate decompose flags against task count.
2. Build label-only launch plan; construct `TaskBoardSettings` including `allow_decompose` and `max_subtasks`.
3. Filter env, prepare session, buy admission, verify grant, `verify_online`.
4. Runner executes a mutable-board loop: for each index, build the isolated decompose prompt, run one fresh agent, parse the decompose block, splice children in place or record a normal step, continue until the mutable board is exhausted or caps stop it.

One fresh agent per attempted task; decomposed children are normal tasks with no further decompose rights.

## 6. Detailed Design

### 6.1 CLI types (`src/vidbyte_cli/types/runtime.py`)

Extend `TaskBoardSettings` (frozen, extra-forbid) with two fields carrying rich `Field(description=...)` help text:

- `allow_decompose: bool` (default `False`).
- `max_subtasks: int` (`ge=2, le=10`, default `5`).

Add a pydantic model validator: `max_subtasks` above 2 with `allow_decompose is False` is allowed at the model layer (the command warns, not the model), so the model stays reusable; the command owns the UX warning.

### 6.2 CLI command (`src/vidbyte_cli/commands/runtime/task_board.py`)

Class `TaskBoardCommand` gains two options on `register()`:

- `--allow-decompose / --no-allow-decompose` (default off) with 4+ sentence help: isolated-only behavior, in-place splice semantics with a 3-becomes-5 example, depth-one rule, cap behavior, and that window/summary flags are ignored when on.
- `--max-subtasks` (`click.IntRange(2, 10)`, default 5) with 4+ sentence help: per-parent bound, self-containment requirement, dedupe and truncation rules, total-board cap interaction, and that it does nothing unless decomposition is on.

`execute()` gains `allow_decompose: bool` and `max_subtasks: int` parameters and passes them into `_settings()`. When decomposition is on, it emits one stderr diagnostic noting that windowed context is disabled. `_COMMAND_HELP` gains two sentences describing decomposition so the positional-argument rule keeps passing C001.

### 6.3 CLI runtime library (`src/vidbyte_cli/lib/runtime_primitives/task_board.py`)

No new top-level functions; one small value class plus private session methods:

- Class `TaskBoardDecomposeParser` with methods `parse_final_text(final_text, max_subtasks)` returning a validated tuple of subtasks (empty tuple means no decomposition), plus helpers `extract_block`, `clean_candidate`, and `dedupe_candidates`. Accepts one ```decompose fenced JSON-array block; strips whitespace; drops empties, over-long entries, and case-insensitive duplicates; truncates to `max_subtasks`. Never raises on model output; malformed JSON returns empty.
- `TaskBoardCodexSession._run` branches: if `settings.allow_decompose` is true, run `_run_decomposing` over a mutable task list; else the existing linear loop verbatim.
- `_run_decomposing(plan, settings, admission_id)` — iterates a mutable `work: list[str]` with an index cursor plus a `depth: dict[int, int]` map keyed by board identity; for each task calls existing `_run_task` with an isolated decompose prompt; on success parses the reply text; depth-0 parents with a non-empty parse splice children via `_splice_subtasks` and record a parent decomposition step; depth-1 children ignore parses. Enforces the 500-task cap by truncating the splice. Emits the same `TASK_STARTING` / `TASK_RETRYING` / `COMPLETE` progress.
- `_splice_subtasks(work, index, subtasks)` — replaces `work[index]` with the subtask list in order; returns the child index range for step recording.
- `_build_prompt` gains the decompose branch: isolated prompt plus a short decompose contract footer naming `max_subtasks`, the fenced-block format, self-containment, and the depth-one rule. Window is not consulted.
- `_build_agent` unchanged except that the SDK seam is used for tool translation when available: the session constructs one lightweight decompose tool description through the SDK translator for prompt rendering only, falling back to the static footer when the SDK is absent so `--help` stays offline.

Thread identity, timeout, summarization markers, and failure placeholders are unchanged. Decompose blocks are stripped from stored summaries so board text stays clean.

### 6.4 Prompt asset (`src/vidbyte_cli/lib/runtime_primitives/task_board_system.md`)

Append a `Decompose contract` section used when decomposition is on: the agent sees only its task, writes normal outcome text first, optionally appends one ```decompose block with 2–N self-contained subtasks that replace the current task at its index, never invents sibling work, and knows children cannot decompose further.

### 6.5 Errors (`src/vidbyte_cli/lib/errors/failures.py`)

Class `TaskBoardDecomposeInvalid(CliError)` (`INVALID_ARGUMENT` / `USAGE`) with static prose: accepts only the documented flag combination and fenced-block shape; rejected before credentials, payment, or execution; hint shows `--allow-decompose --max-subtasks 5` and `runtime task-board --help`. Used for flag misuse (e.g. future dag conflicts); malformed model output never raises it.

### 6.6 Untouched layers

- `RuntimeLaunchPlanner.build_task_board`, `RuntimeAdmissionGate._ALLOWED_PRICES`, `RuntimeExecutor.execute_task_board`, `RuntimeEndpoints.admit_task_board`: unchanged.
- Backend (`vidbyte` repo): no change. Same capability, price, route, and grant shape.

## 7. Data Model Changes

- N/A — No Mongo collections, indexes, ledger, or backend DTO changes.
- Pydantic-only: two new `TaskBoardSettings` fields (§6.1); `TaskBoardStepResult` / `TaskBoardResult` shapes unchanged.

## 8. API Changes

- N/A — No new routes, no price or permission changes.
- CLI surface only: `vidbyte-cli runtime task-board [--allow-decompose] [--max-subtasks N]`.

## 9. File Change Manifest

- CREATE `docs/design/task-board-decompose.md` — this doc.
- CREATE `scripts/test-task-board-decompose.py` — Phase 5 verification script.
- MODIFY `src/vidbyte_cli/types/runtime.py` — decompose fields and validators.
- MODIFY `src/vidbyte_cli/commands/runtime/task_board.py` — flags, wiring, help copy.
- MODIFY `src/vidbyte_cli/lib/runtime_primitives/task_board.py` — parser plus decomposing run/splice/prompt branches.
- MODIFY `src/vidbyte_cli/lib/runtime_primitives/task_board_system.md` — decompose contract section.
- MODIFY `src/vidbyte_cli/lib/errors/failures.py` — `TaskBoardDecomposeInvalid`.
- MODIFY `scripts/run_ci.py` — register the new verification script as a source gate.

Count: create 2, modify 6, delete 0.

## 10. Testing Plan

Executed via `scripts/test-task-board-decompose.py` (offline, fake SDK transport), plus the existing `scripts/test-task-board.py` re-run for linear regression.

- [Edge Case] Decomposition off by default: settings without flags report `allow_decompose is False` and existing prompts render byte-identical.
- [Edge Case] Single task decomposing into exactly `max_subtasks` completes with K children in order.
- [Edge Case] Minimum `--max-subtasks 2` with 2 candidates splices both; 1 candidate is dropped as below minimum.
- [Edge Case] Empty board-adjacent inputs still rejected before decomposition logic runs.
- [Hidden Failure] Mid-board `CodexAgentError` on a parent records failure and never splices partial subtasks.
- [Hidden Failure] Retry success on second attempt yields exactly one splice, never duplicates.
- [Hidden Failure] Total cap: a splice that would exceed 500 tasks truncates to fit and notes truncation on stderr.
- [Silent Failure] Splice positions are exact: decomposing index 1 of `[A, B, C]` into 3 yields `[A, K1, K2, K3, C]` in execution order with correct step indices.
- [Silent Failure] Isolation holds: child prompts contain only their own subtask text, never sibling tasks or parent summaries; assert prompt bodies exactly.
- [Silent Failure] Depth-one holds: a child carrying its own decompose block executes as normal work with the block ignored and stripped from its summary.
- [Silent Failure] Dedupe works: case-insensitive duplicate subtasks collapse to one entry preserving first-seen order.
- [Silent Failure] Over-long subtasks (>20k chars) are dropped while valid siblings splice.
- [Silent Failure] Malformed blocks (no fence, bad JSON, JSON object instead of array, non-string entries) yield no decomposition and a normal completed step.
- [Silent Failure] `--window` ignored when on: window 0 vs 10 render identical decompose prompts.
- [Hidden Assumption] Task text containing `{{...}}` braces is never interpolated.
- [Hidden Assumption] Decompose blocks are stripped from stored step summaries and board text.
- [Hidden Assumption] Runner receives the verified grant and performs zero admit/verify calls during `execute_task_board` in decompose mode.
- [Hidden Assumption] Linear regression: existing `scripts/test-task-board.py` still exits 0 unchanged.

## 11. Dependencies

- In-repo only: `click`, `pydantic`, lazy `vidbyte-sdk` `CodexHarnessAgent` plus the new custom-tool translator for prompt rendering (static fallback keeps `--help` offline).
- No new packages, no backend deploy, no pricing review (price unchanged).

## 12. Rollout

1. Land CLI-only change behind default off; `runtime task-board --help` shows the new options with no behavior change for existing invocations.
2. Smoke locally: 3-task board `--allow-decompose --max-subtasks 3` where task 2 decomposes; confirm stdout holds only the final result.
3. Run `python scripts/test-task-board-decompose.py`, existing `scripts/test-task-board.py`, `python lint/run.py --rule C001 --all`, then full `python scripts/run_ci.py` before PR.

## 13. Open Questions

- Q1: Should children inherit the parent task as prefix context, or stay strictly isolated with self-contained subtasks only?
- Q2: Should a future `--max-depth` allow recursive decomposition, and what cap prevents runaway fan-out?
- Q3: When DAG mode lands, do decomposed children inherit the parent's parents, replace them, or link only to the parent?

## 14. Alternatives Considered

- A1: Children appended at end instead of in-place splice. Rejected because position carries meaning on a task board; end-append breaks the "at its own index" requirement and scrambles dependency order.
- A2: Parent kept plus children appended after it. Rejected because the parent's work is the decomposition itself; keeping it doubles execution and confuses completion accounting.
- A3: Real-time MCP `decompose_tool` calls mid-turn. Rejected for v1 because the pinned Codex SDK exposes no tool registration seam; the outer-loop envelope gives the same board mutation with offline testability and no sidecar process.
- A4: Separate `task-board-decompose` subcommand. Rejected because it duplicates every shared option and splits one primitive's help in two; flags keep one command, one admission, and one result shape.
