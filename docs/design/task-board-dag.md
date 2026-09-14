# Design Doc — Task Board DAG Dependencies (`--type linear|dag`)

## 1. Overview

Add dependency links to the `runtime task-board` command so a board can run as a directed
acyclic graph (DAG) instead of one fixed linear order. Today task 8 always waits for tasks
0–7 and every agent reads summaries of the immediately preceding `--window` tasks, even when
task 8 only needs task 2. That pays for unrelated context and serializes independent work
behind unrelated predecessors.

This change adds a `--type` selector (`linear` | `dag`, default `linear`) that determines the
structure of the execute loop, plus repeatable `--depends-on` links (`CHILD:PARENT[,PARENT...]`)
that declare the DAG. `linear` preserves the current loop exactly. `dag` runs tasks in
deterministic topological order and gives each agent only its direct dependencies' summaries.
Execution stays sequential (one fresh `CodexHarnessAgent` per task, one flat 2c admission);
parallel fan-out is explicitly deferred. The win in v1 is correctness of ordering plus bounded,
relevant context — not wall-clock parallelism.

## 2. Goals / Non-Goals

### Goals

- Add `--type linear|dag` (default `linear`) selecting the execute-loop structure.
- Add repeatable `--depends-on CHILD:PARENT[,PARENT...]` declaring DAG edges by 0-based board
  index, validated before admission.
- Run `dag` boards in deterministic topological order (Kahn's algorithm, smallest-index
  tie-break) with per-task context limited to direct dependencies' summaries.
- Keep `linear` behavior byte-identical to today, including window slicing and progress copy.
- Reject malformed links, out-of-range indices, self-edges, duplicate edges, cycles, and any
  `--depends-on` combined with `--type linear` before credentials, payment, or execution.
- Preserve the PR #32 gateway order, fresh-agent-per-task isolation, retry semantics, and the
  stdout-is-results-only contract.

### Non-Goals

- N/A — Parallel/concurrent execution of ready tasks is out of scope; v1 runs the DAG
  sequentially in topological order so admission, env filtering, and the SDK session stay
  unchanged. Parallelism is a follow-up with its own admission and safety review.
- N/A — LLM-based summarization; per-dependency summaries reuse the deterministic
  `truncate-tail` / `head-tail` summarizer with no model calls.
- N/A — Backend changes; no catalog, route, pricing, or ledger change. Admission stays one
  flat 2c `runtime.task-board@1` grant covering the whole board.
- N/A — New task-source shapes; board input stays literal `TASKS...` or repeatable
  `--task-file`, never mixed.

## 3. Background

`runtime task-board` (design `docs/design/task-board.md`, shipped in PR #39) models a board as
an ordered tuple of task strings. `TaskBoardCommand.execute()` validates locally, builds a
label-only `RuntimeLaunchPlan`, constructs frozen `TaskBoardSettings`, filters provider env,
prepares `TaskBoardCodexSession`, buys one admission, verifies the grant, then delegates to
`RuntimeExecutor.execute_task_board()`, which runs the network-free loop. The session's `_run`
loops `enumerate(settings.tasks)` in order; `_build_prompt` renders `summaries[max(0,i-window):i]`
(or nothing in `isolated` mode) through `TaskBoardSummarizer`.

Field-guide constraints applied: `field-guide/vidbyte-cli/runtime-execution.md` (verify grant in
the command before the runner starts; runner takes SDK plus grant and holds no endpoints;
fresh agents so threads never leak), `field-guide/vidbyte-cli/typed-failures.md` (no standalone
functions; new failures are `CliError` subclasses in `lib/errors/failures.py`),
`field-guide/vidbyte-cli/implementation-restraint.md` (match comment density, touch only listed
files, private methods over collaborator classes, canonical `python scripts/run_ci.py` gate),
`field-guide/vidbyte-cli/agent-facing-lint-suite.md` (every new option needs four-sentence help;
prove the lint rule still passes).

AGENTS.md notes: stdout is results-only with `OutputDocument(kind="runtime.task-board")`;
entry functions return int status; CLI is a thin transport layer — dependency resolution is
local planning, not research logic, so it belongs in `lib/runtime_primitives/`.

## 4. Requirements

### Functional

- R1: CLI accepts `--type` with choices `linear` (default) and `dag`.
- R2: CLI accepts repeatable `--depends-on` with grammar
  `CHILD:PARENT[,PARENT...]`, all non-negative integers, no spaces required, e.g.
  `--depends-on 8:2 --depends-on 5:2,3`. Each pair is one directed edge parent → child.
- R3: Edge indices reference 0-based board positions. Child and every parent must satisfy
  `0 <= idx < len(tasks)`. Self-edges, duplicate edges, and malformed specs are rejected.
- R4: Any `--depends-on` with `--type linear` is rejected (fail closed, no silent ignore).
- R5: `--type dag` validates the edge set is acyclic before admission; a cycle is rejected
  with the dependency error, naming nothing but the contract.
- R6: `linear` execution is unchanged: index order 0..N-1, window slice context, existing
  progress and retry behavior.
- R7: `dag` execution runs tasks once each in topological order (Kahn, smallest ready index
  first, stable across runs). Context for task `c` with parents `P(c)` is the summaries of
  exactly `P(c)` sorted by parent index, each passed through the same per-summary
  `summarize(mode, summary_max_chars)`; tasks with no parents get the same empty-context
  rendering linear uses (`(no prior results)` in windowed mode, no section in isolated mode).
- R8: `--window` is ignored for context selection in `dag` mode (documented in help); windowed
  vs isolated `context_mode` still applies. `--summary-mode` / `--summary-max-chars` still
  shape each per-dependency summary in both types.
- R9: Failure policy in `dag`: a task that exhausts retries is recorded `failed` with a
  reason-carrying summary (attempt count, failure kind, and any partial agent text the last
  turn left behind), still prefixed `Task {index} failed.`. With `stop_on_error=true` the
  board halts at the first failure. With `false`, any not-yet-run task that transitively
  depends on a failed task is marked `failed` without spawning an agent (dependency-skip),
  its summary naming the failed parents; independent tasks still run. Linear `failed`
  summaries keep the exact placeholder so windowed prompts are unchanged.
- R10: Result shape unchanged: `TaskBoardResult` with per-step `index`, `task`, `summary`,
  `status`, `thread_id`. In `dag` mode `steps` are ordered by execution (topological) order;
  each step carries its board `index` so callers can re-sort.
- R11: All dependency validation happens before `CREDENTIALS`/admission, alongside existing
  board validation, so bad graphs never touch payment.

### Non-functional

- Offline-testable resolver and prompt selection with zero network or SDK imports.
- Strict typing (`mypy`), `ruff check`, `ruff format`, `python lint/run.py` (C001 help depth for
  two new options), and `python scripts/run_ci.py` green.
- No secrets or task text in errors or progress; diagnostics on stderr only.

## 5. High-Level Design

No backend work. CLI-only change mirroring the existing layers: types → errors → session
(private DAG methods) → command (options, parsing, settings construction). The planner, gate,
executor, and admission client are untouched except where imports demand it; the executor keeps
delegating to `session.run()` and the session branches internally on `settings.execution_type`.

Flow per invocation (both types share everything except the final loop):

1. Validate idempotency key, resolve board source, parse `--depends-on` against task count.
2. Build label-only launch plan; construct `TaskBoardSettings` including `execution_type` and
   normalized `dependencies`.
3. Filter env, prepare session, buy admission, verify grant, `verify_online`.
4. Runner executes: linear → existing index loop; dag → topological loop with dep-only context.

One fresh agent per attempted task in both modes; dependency-skipped tasks spawn no agent.

## 6. Detailed Design

### 6.1 CLI types (`src/vidbyte_cli/types/runtime.py`)

Class `TaskBoardExecutionType(StrEnum)` with `LINEAR="linear"`, `DAG="dag"`.

Extend `TaskBoardSettings` (frozen, extra-forbid) with two fields carrying rich
`Field(description=...)` help text:

- `execution_type: TaskBoardExecutionType` (default `LINEAR`).
- `dependencies: tuple[tuple[int, int], ...]` (default `()`), normalized sorted unique
  `(child, parent)` edges. Validators reject: non-`linear`/`dag` mismatch is a command-layer
  concern, but the model itself rejects negative indices, `child == parent`, duplicates, and
  cycles (Kahn over `len(tasks)` nodes; unresolvable remainder means a cycle). Model validators
  also reject edges whose indices fall outside `len(tasks)` so a settings object can never
  describe a dangling link even when constructed outside the command.

`TaskBoardSummaryMode`, `TaskBoardContextMode`, limits, and result DTOs are unchanged.

### 6.2 CLI command (`src/vidbyte_cli/commands/runtime/task_board.py`)

Class `TaskBoardCommand` gains two options on `register()`:

- `--type` (`click.Choice(("linear", "dag"))`, default `linear`) with ≥4-sentence help:
  what each mode does to order and context, that linear is the default preserving current
  behavior, that dag ignores `--window` for context selection, that execution stays sequential
  in v1 with no parallel fan-out.
- `--depends-on` (`multiple=True`, default `()`), each value matching
  `CHILD:PARENT[,PARENT...]`, with ≥4-sentence help: index base, repeatability, accumulation
  across repeats (`--depends-on 5:2 --depends-on 5:3` equals `--depends-on 5:2,3`), rejection
  rules, and that it requires `--type dag`.

`execute()` gains `execution_type: str` and `depends_on: tuple[str, ...]` parameters (single-line
signatures per repo style) and calls a private `_parse_dependencies(raw, task_count)` method
before plan construction:

- Splits each raw spec on `:` exactly once, then parents on `,`; strips whitespace; rejects
  empty fragments, non-digits, and negative forms with `TaskBoardDependencyInvalid`.
- Builds `(child, parent)` pairs; rejects self-edges, out-of-range indices, and duplicates.
- Rejects non-empty `raw` when `execution_type == "linear"`.
- Returns a sorted tuple of unique pairs; cycle detection is left to `TaskBoardSettings`
  validation (single source of truth), whose error the command lets propagate as the same
  dependency failure.

`_settings()` gains the two new arguments and maps them onto `TaskBoardExecutionType` plus the
parsed edge tuple. `_COMMAND_HELP` is extended with two sentences describing the type selector
so the positional-argument rule (command help names its task source) keeps passing C001.

### 6.3 CLI runtime library (`src/vidbyte_cli/lib/runtime_primitives/task_board.py`)

No new classes (per single-use-helper restraint); three private methods on
`TaskBoardCodexSession` plus a branch in `_run` / `_build_prompt`:

- `_run` branches: `if settings.execution_type is TaskBoardExecutionType.DAG` → `_run_dag`,
  else the existing linear loop verbatim.
- `_topological_order(count, edges)` — Kahn's algorithm with a sorted ready list
  (smallest index first); raises `TaskBoardDependencyInvalid` if output is short (cycle).
  Pure over ints, no SDK import, directly unit-testable.
- `_run_dag(plan, settings, admission_id)` — sizes `slots` to N board-indexed summary
  strings and a `failed: set[int]`; iterates `_topological_order`; for each index: looks up
  direct parents via `_dag_parents`; if any parent failed, records a dependency-skip failed
  step naming the blocking parents with no agent call, emits `TASK_SKIPPED`, applies
  `stop_on_error`, continues; else calls `_run_task_detailed` with the board-indexed slots,
  records completed/failed, emits `TASK_FAILED` with a reason-carrying summary on agent
  failure, applies `stop_on_error`. Emits `TASK_STARTING`, then `DAG_PLAN_READY` once the
  parent map is built, then `COMPLETE`. Returns steps in execution order via `_result`.
- `_build_prompt` gains the DAG branch: looks up `parents(c)` sorted, collects
  `(p, summaries[p])` for completed parents (all present by topological invariant), renders via
  existing `render_context` / `render_prompt`. Isolated mode still returns the `None`-context
  prompt. Window is not consulted in DAG mode.

`_run_task` keeps its signature and delegates to `_run_task_detailed`, which returns the
same result plus a failure note (attempt count, timeout vs host kind, bounded partial agent
text from an incomplete turn). The DAG loop records the note via `_failed_dag_step`; the
linear loop ignores it, so linear summaries, prompts, and progress are byte-identical.

Thread identity, timeout, summarization markers, and the linear placeholder text
(`f"Task {index} failed."`) are unchanged; DAG `failed` summaries extend that prefix with
the skip or attempt detail.

### 6.4 Errors (`src/vidbyte_cli/lib/errors/failures.py`)

Class `TaskBoardDependencyInvalid(CliError)` (`INVALID_ARGUMENT` / `USAGE`) with static prose:
accepts only `CHILD:PARENT[,PARENT...]` 0-based links within the board, no self-links,
duplicates, linear-mode links, or cycles; rejected before credentials, payment, or execution;
hint shows the `--depends-on 8:2` form and `runtime task-board --help`.

### 6.5 Untouched layers

- `RuntimeLaunchPlanner.build_task_board`, `RuntimeAdmissionGate._ALLOWED_PRICES`,
  `RuntimeExecutor.execute_task_board`, `RuntimeEndpoints.admit_task_board`: unchanged. The
  executor still gates on the verified verdict and delegates to `session.run()`.
- Backend (`vidbyte` repo): no change. Same capability, price, route, and grant shape.

## 7. Data Model Changes

- N/A — No Mongo collections, indexes, ledger, or backend DTO changes.
- Pydantic-only: `TaskBoardExecutionType` plus two new `TaskBoardSettings` fields (§6.1);
  `TaskBoardStepResult` / `TaskBoardResult` shapes unchanged.

## 8. API Changes

- N/A — No new routes, no price or permission changes.
- CLI surface only: `vidbyte-cli runtime task-board [--type linear|dag] [--depends-on ...]`.
  Admission stays `POST /api/x402/runtime/task-board/activate` at 2c with the existing client.

## 9. File Change Manifest

- CREATE `docs/design/task-board-dag.md` — this doc.
- CREATE `scripts/test-task-board-dag.py` — Phase 5 verification script.
- MODIFY `src/vidbyte_cli/types/runtime.py` — execution-type enum plus settings fields and
  validators.
- MODIFY `src/vidbyte_cli/commands/runtime/task_board.py` — `--type` / `--depends-on`
  options, parsing helper, settings wiring, help copy.
- MODIFY `src/vidbyte_cli/lib/runtime_primitives/task_board.py` — topological order plus DAG
  run/prompt branches.
- MODIFY `src/vidbyte_cli/lib/errors/failures.py` — `TaskBoardDependencyInvalid`.
- MODIFY `scripts/run_ci.py` — register the new verification script as a source gate.

Count: create 2, modify 5, delete 0.

## 10. Testing Plan

Executed via `scripts/test-task-board-dag.py` (offline, fake SDK transport), plus the existing
`scripts/test-task-board.py` re-run for linear regression. Every case below runs in the new
script unless marked otherwise.

- [Edge Case] `--type linear` default preserved: settings constructed without flags report
  `execution_type == linear` and empty dependencies.
- [Edge Case] `--depends-on` with `--type linear` rejected before admission.
- [Edge Case] Malformed specs rejected: `8`, `8:`, `:2`, `8-2`, `a:b`, `8:2.5`, empty string.
- [Edge Case] Out-of-range indices rejected: child or parent `>= len(tasks)` and negative forms.
- [Edge Case] Self-edge `3:3` rejected; duplicate edge across repeats (`5:2` twice) rejected.
- [Edge Case] DAG with zero edges runs in board order with `(no prior results)` markers
  (windowed) and section-free prompts (isolated).
- [Edge Case] Single task with `--type dag` and no deps completes with empty dep context.
- [Hidden Failure] Cycle `0:1, 1:0` and longer cycle `0:1, 1:2, 2:0` rejected before any agent
  starts (network hits == 0).
- [Hidden Failure] Mid-DAG `CodexAgentError` with `stop_on_error=true` halts; with `false`
  the failed step is recorded and only its transitive dependents skip while independent tasks
  still complete.
- [Hidden Failure] Retry success on second attempt yields exactly one step entry.
- [Hidden Failure] Dependency-skip spawns no agent (fake transport call count excludes skipped
  indices) and keeps board indices aligned via placeholder summaries.
- [Silent Failure] Task 8 with sole dep `8:2` sees exactly summary `[2]`, never `[0]`, `[1]`,
  or `[3..7]`; assert exact ID labels in the rendered prompt.
- [Silent Failure] Topological tie-break is deterministic: independent tasks execute in
  smallest-index-first order across repeated runs.
- [Silent Failure] `head-tail` vs `truncate-tail` per-dep summaries keep their existing split
  semantics inside DAG prompts; over-limit dep summaries carry the truncation marker.
- [Silent Failure] Thread IDs unique per attempted step; skipped steps use the deterministic
  `task-board-{index}-failed` placeholder and never reuse a live thread.
- [Silent Failure] `--window` ignored in DAG: window 0 vs 10 with identical deps render
  identical prompts.
- [Hidden Assumption] Task text containing `{{...}}` braces is never interpolated.
- [Hidden Assumption] Isolated DAG prompts carry no prior-results section at all.
- [Hidden Assumption] Runner receives the verified grant and performs zero admit/verify calls
  during `execute_task_board` in DAG mode.
- [Hidden Assumption] Linear regression: existing `scripts/test-task-board.py` still exits 0
  unchanged.

## 11. Dependencies

- In-repo only: `click`, `pydantic`, lazy `vidbyte-sdk` `CodexHarnessAgent` (unchanged import
  sites so `--help` stays offline).
- No new packages, no backend deploy, no pricing review (price unchanged).

## 12. Rollout

1. Land CLI-only change behind default `linear`; `runtime task-board --help` shows the new
   options with no behavior change for existing invocations.
2. Smoke locally: 4-task board `--type dag --depends-on 2:0 --depends-on 3:1` completes with
   each agent reading only its parent; confirm stdout holds only the final result.
3. Run `python scripts/test-task-board-dag.py`, existing `scripts/test-task-board.py`,
   `python lint/run.py --rule C001 --all`, then full `python scripts/run_ci.py` before PR.

## 13. Open Questions

- Q1: Should a future `--depends-file` (JSON/YAML edge list) exist for large graphs, or is
  repeatable `--depends-on` sufficient up to 500 tasks?
- Q2: When parallel execution lands, should the result order stay topological-execution order
  or switch to board-index order, and should `--max-parallel` be a new setting?
- Q3: Should `--window` in DAG mode cap the parent set (most-recent N parents) instead of
  being ignored, once boards with very wide fan-in appear?

## 14. Alternatives Considered

- A1: `--dag-file` JSON graph instead of `--depends-on` flags. Rejected for v1 because flags
  compose with existing `--task-file` boards, need no new file schema, and stay greppable in
  shell history; a file form can layer on later without breaking flags.
- A2: Transitive-closure context (task sees all ancestors, not just direct parents). Rejected
  because it reintroduces the unrelated-context cost this feature removes; direct parents plus
  each parent's own summarized work already propagate what matters through bounded summaries.
- A3: Parallel ready-task execution now. Rejected because agent concurrency, shared env, and
  progress accounting need their own safety review; sequential topological order captures the
  ordering and context wins with zero new runtime hazards.
- A4: Separate `task-board-dag` subcommand instead of `--type`. Rejected because it duplicates
  every shared option and splits one primitive's help in two; a type selector keeps one command,
  one admission, and one result shape.
