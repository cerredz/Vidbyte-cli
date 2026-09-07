# Design Doc — Task Board Runtime Primitive

## 1. Overview

Add a `runtime.task-board@1` local runtime primitive spanning `vidbyte` (service-level x402 admission) and `vidbyte-cli` (settings, verification gateway, sequential execution).

The primitive models a task board as an ordered array of string tasks. One separate `CodexHarnessAgent` executes each task in order. Context passed to agent N is never raw full history. It is always a bounded summary of the previous `window` task results, shaped by explicit summary settings. For example, with 100 tasks and `window=10`, the agent for task 90 sees summaries of task results 80–89 plus its own task 90.

## 2. Goals / Non-Goals

### Goals

- Register a flat-price `runtime.task-board@1` x402 capability in `vidbyte` with a mounted admission handler and grant verification reuse.
- Define frozen, richly documented `TaskBoardSettings` plus result DTOs in `vidbyte-cli` with window and summary behavior as first-class settings.
- Implement sequential per-task execution in `vidbyte-cli` using the PR #32 verification gateway order (validate key, build plan, check host, load SDK, buy admission, `verify_online`, then run with no network in the runner).
- Spawn one separate `CodexHarnessAgent` per task, each receiving current task plus windowed summaries.
- Provide a `vidbyte-cli runtime task-board` command with rich `--help` descriptions for every setting.

### Non-Goals

- N/A — Parallel or DAG execution is out of scope; v1 is strictly sequential so window semantics stay deterministic.
- N/A — LLM-based summarization of prior results is out of scope; v1 uses deterministic truncation/head-tail summarization so tests run offline.
- N/A — Durable backend execution, Inngest orchestration, or Mongo persistence of task content; execution stays local per runtime-primitive policy.
- N/A — Frontend (`next-app`) surfaces; no server action or page is added.

## 3. Background

`vidbyte-cli` already ships `runtime.persistence@1` as the reference local primitive: `RuntimeLaunchPlanner.build()` validates task/host/cwd, `PersistenceCommand.execute()` follows verify-before-run, `RuntimeAdmissionGate.verify_online()` checks the backend-verified grant, and `RuntimeExecutor.execute_persistence()` enforces admission at the final boundary before `PersistentCodexSession` drives `CodexHarnessAgent` turns.

`vidbyte` backend already mounts four runtime admissions in `backend/routes/x402_runtime.py` backed by immutable `X402CapabilityDefinition` entries in `backend/lib/x402/catalog.py` and a single `RuntimeAdmissionService.admit/verify` path. The catalog validates identity, payment mode, and local-execution metadata at import time.

Field-guide constraints applied: `field-guide/vidbyte-cli/runtime-execution.md` (one SDK agent pattern, env merging, typed policy results, verify-grant-in-command-before-runner), `field-guide/vidbyte-cli/typed-failures.md` (no standalone functions), `field-guide/vidbyte/route-pricing-precision.md` ($0.01 minimum, whole cents only), and `field-guide/vidbyte/harness-anatomy.md` (model-facing copy review).

AGENTS.md notes: `vidbyte-cli/AGENTS.md` — stdout is results-only, entry function returns int status, thin transport layer. `vidbyte/AGENTS.md` — routes thin, orchestrators sequence, services own logic, database layer owns Mongo; no task content in ledger metadata.

## 4. Requirements

### Functional

- R1: `vidbyte` catalog declares `runtime.task-board@1` v1 as `PREPAID_WALLET_FLAT`, 2 cents, `lifecycle=DURABLE_ASYNC`, `path=/api/x402/runtime/task-board/activate`, `permission=runtime:write`, `execution_location=local`, `supported_hosts=(codex,)`.
- R2: `vidbyte` mounts `POST /api/x402/runtime/task-board/activate` delegating to `svc.admit(..., "runtime.task-board@1")`; existing `/grants/verify` covers verification with no new verify route.
- R3: `RuntimeAdmissionService` rejects non-codex hosts for task-board, mirroring the persistence guard.
- R4: CLI accepts an ordered task list (repeatable `--task` and/or `--tasks-file` with one task per line), `window` (0–25, default 10), `summary-mode` (`truncate-tail` | `head-tail`, default `truncate-tail`), `summary-max-chars` (100–8000, default 1200), `stop-on-error` (default true), `retries-per-task` (0–3, default 1).
- R5: Executor runs tasks sequentially from index 0; agent i receives task i plus summaries of `results[max(0,i-window):i]`; each task runs in its own `CodexHarnessAgent` thread; thread identity must not leak across tasks.
- R6: Summarization is always applied; raw prior results never enter the next prompt unsummarized. `truncate-tail` keeps a prefix plus `...[truncated N chars]`; `head-tail` keeps head+`...`+tail split evenly.
- R7: Command follows PR #32 gateway order and passes verified grant plus loaded SDK into a network-free runner.
- R8: `runtime list` surfaces the new capability automatically via catalog projection; CLI `_ALLOWED_PRICES` admits it at 2 cents.

### Non-functional

- Offline-testable summarizer and prompt renderer with zero network or SDK imports.
- Strict typing (`mypy`), `ruff check`, `ruff format`, and `python scripts/run_ci.py` green in `vidbyte-cli`; `python lint/run.py` green in `vidbyte`.
- No secrets in stdout; diagnostics on stderr via existing `OutputManager.diagnostic`.

## 5. High-Level Design

Backend change is additive catalog + one thin route. CLI change mirrors persistence: types → constants → summarizer/session → planner/gate/executor/endpoints → command.

Execution flow per invocation:

1. Parse and validate settings locally (free).
2. Build one `RuntimeLaunchPlan` with `capability_id=runtime.task-board@1` carrying a board label, not full task text.
3. Prepare SDK session (construct settings, no model turn).
4. Buy admission, `verify_online`, then loop tasks sequentially, each in a fresh agent with windowed summaries.

One fresh agent per task is the core isolation choice. It trades thread-resume efficiency for deterministic context: the only cross-task channel is the Vidbyte-built summary block.

## 6. Detailed Design

### 6.1 Backend (`vidbyte` repo)

- `backend/lib/x402/catalog.py`: append `runtime.task-board@1` entry with `@intent runtime-primitive-flat-price-because-execution-is-caller-local` comment mirroring persistence/ensemble entries.
- `backend/routes/x402_runtime.py`: add `activate_task_board` POST handler; update module docstring inventory from four to five handlers.
- `backend/services/runtime_primitives/admission.py`: extend host guard to `if capability_key in ("runtime.persistence@1", "runtime.task-board@1") and body.host != "codex"`.

No orchestrator, database, or ledger shape change. `record_usage` metadata stays `{"capability_id", "host"}` only.

### 6.2 CLI types (`src/vidbyte_cli/types/runtime.py`)

Class `TaskBoardSummaryMode(StrEnum)` with `TRUNCATE_TAIL="truncate-tail"`, `HEAD_TAIL="head-tail"`.

Class `TaskBoardSettings(BaseModel, frozen, extra=forbid)` with `Field(description=...)` rich help text per field:

- `tasks: tuple[str, ...]` (1–500 items, each 1–4000 chars).
- `window: int` (0–25).
- `summary_mode: TaskBoardSummaryMode`.
- `summary_max_chars: int` (100–8000).
- `stop_on_error: bool`.
- `max_retries_per_task: int` (0–3).

Classes `TaskBoardStepResult` (`index`, `task`, `summary`, `status: Literal["completed","failed"]`, `thread_id`) and `TaskBoardResult` (`admission_id`, `completed`, `failed`, `steps: tuple[TaskBoardStepResult, ...]`, `text` = joined summaries) as frozen models.

Extend `RuntimeLaunchPlan.capability_id` Literal with `"runtime.task-board@1"`.

### 6.3 CLI constants (`src/vidbyte_cli/lib/constants/runtime.py`)

- `TaskBoardLimit(IntEnum)`: `TURN_TIMEOUT_SECONDS=3600`, `MAX_TASKS=500`, `MAX_TASK_CHARS=4000`, `MAX_WINDOW=25`.
- `TaskBoardProgress(StrEnum)`: `PREPARING`, `CREDENTIALS`, `ADMISSION`, `VERIFYING`, `ADMITTED`, `TASK_STARTING` (no indices per field guide — phase copy only), `TASK_RETRYING`, `COMPLETE`.
- `TaskBoardCodexConfig(StrEnum)`: same five child-only provider overrides as persistence.

### 6.4 CLI runtime library (`src/vidbyte_cli/lib/runtime_primitives/`)

Class `TaskBoardSummarizer` (pure, no SDK import):

- `summarize(text: str, mode: TaskBoardSummaryMode, limit: int) -> str` — composes trimming.
- `render_context(summaries: ..., mode, limit) -> str` — joins labeled `[i]` lines.
- `render_prompt(task, index, context) -> str` — fixed template with current task plus summary block or `(no prior results)`.

Class `TaskBoardCodexSession` (mirrors `PersistentCodexSession`):

- `prepare(plan: Plan) -> None` — builds one `CodexHarnessAgent` factory config (client bin/cwd/env + workspace-write sandbox); no model turn.
- `run(plan: Plan, settings: TaskBoardSettings) -> TaskBoardResult` — sync wrapper over `asyncio.run`, mapping `CodexAgentError`/TimeoutError to `TaskBoardHostFailed`.
- `run_step(task, prompt) -> AgentMessage` — one fresh agent per call with timeout; validates `status==completed` and non-empty `thread_id`/`final_response`.

Class `RuntimeExecutor.execute_task_board(plan, settings, session, verdict) -> TaskBoardResult` — final admission gate plus capability check, then delegates to session. Keeps the same `_require_verdict` semantics.

`RuntimeLaunchPlanner`: extend `Product` Literal with `"runtime.task-board@1"`; add `build_task_board(tasks, host, cwd, capability_id) -> tuple[Plan, TaskBoardSettings-inputs]` validating count/chars and resolving host/cwd. Plan `task` holds a short board label (e.g. first task truncated) since full board travels in settings, never to the backend.

`RuntimeAdmissionGate._ALLOWED_PRICES`: add `"runtime.task-board@1": 2`.

`RuntimeEndpoints`: add `TASK_BOARD_ADMISSION_PATH="/api/x402/runtime/task-board/activate"` and `admit_task_board(request, key)`.

New prompt assets: `task_board_system.md` (six-section fixed-stage prompt: role, goal, input contract, summary-context contract, output contract, stop conditions) and reuse `continuation.md` pattern is N/A — per-task prompts are rendered, not continued.

### 6.5 CLI command (`src/vidbyte_cli/commands/runtime/task_board.py`)

Class `TaskBoardCommand` with `register(parent)` exposing:

- `TASKS...` arguments or `--tasks-file PATH` (one per line, blank lines skipped).
- `--host` (auto|codex, default codex), `--window`, `--summary-mode`, `--summary-max-chars`, `--stop-on-error/--no-stop-on-error`, `--retries-per-task`, `--idempotency-key`.

`execute()` order: idempotency validate → planner build → settings construct → credentials filter env (same denylist as persistence) → `session.prepare` → `admit_task_board` → grant_token presence check → `verify_grant` → `verify_online` → `execute_task_board` → `OutputDocument(kind="runtime.task-board")`.

Register in `commands/runtime/__init__.py`.

## 7. Data Model Changes

- N/A - No Mongo collections, indexes, or DTO persistence changes. Admission ledger reuses `ApiBillingUsageWrite` with unchanged shape.
- Pydantic-only additions in CLI types (see 6.2); backend DTOs unchanged.

## 8. API Changes

- `GET /api/x402/runtime` projection automatically includes `runtime.task-board@1` (no handler change).
- New `POST /api/x402/runtime/task-board/activate` (flat 2c, idempotent via `Idempotency-Key`, `runtime:write`).
- CLI `RuntimeEndpoints.admit_task_board` typed client for the above.
- CLI command `vidbyte-cli runtime task-board` (new).

## 9. File Change Manifest

Backend (`vidbyte`, 3 modifies, 0 creates):

- MODIFY `backend/lib/x402/catalog.py` — declare `runtime.task-board@1`.
- MODIFY `backend/routes/x402_runtime.py` — mount activate handler.
- MODIFY `backend/services/runtime_primitives/admission.py` — codex-only host guard.

CLI (`vidbyte-cli`, 5 creates, 7 modifies):

- CREATE `src/vidbyte_cli/commands/runtime/task_board.py` — gateway command.
- CREATE `src/vidbyte_cli/lib/runtime_primitives/task_board.py` — summarizer + session.
- CREATE `src/vidbyte_cli/lib/runtime_primitives/task_board_system.md` — stage prompt.
- CREATE `docs/design/task-board.md` — this doc.
- CREATE `scripts/test-task-board.py` — Phase 5 verification script.
- MODIFY `src/vidbyte_cli/types/runtime.py` — settings + results + plan literal.
- MODIFY `src/vidbyte_cli/lib/constants/runtime.py` — limits + progress + codex config.
- MODIFY `src/vidbyte_cli/lib/runtime_primitives/planner.py` — product + builder.
- MODIFY `src/vidbyte_cli/lib/runtime_primitives/gate.py` — allowed price.
- MODIFY `src/vidbyte_cli/lib/runtime_primitives/executor.py` — execute path.
- MODIFY `src/vidbyte_cli/lib/api/endpoints/runtime.py` — admission client.
- MODIFY `src/vidbyte_cli/commands/runtime/__init__.py` — registration.

Count: create 5, modify 10, delete 0.

## 10. Testing Plan

Backend (pytest feature area + catalog import checks):

- [Edge Case] Empty task list rejected before admission.
- [Edge Case] `window=0` yields prompt with `(no prior results)` and no summary block.
- [Edge Case] `window` larger than completed count clamps to available prefix.
- [Hidden Failure] Grant for `runtime.persistence@1` reused against task-board plan is rejected as `CAPABILITY_MISMATCH`.
- [Silent Failure] Catalog lists task-board but route unmounted → startup `ROUTE_TABLE.validate_against_app` fails rather than serving discovery-only product.
- [Hidden Assumption] Non-codex host `claude` is rejected for task-board admission.

CLI (`scripts/test-task-board.py`, offline, fake SDK transport):

- [Edge Case] 500 tasks accepted; 501st rejected.
- [Edge Case] Single task with `window=10` runs with empty context.
- [Edge Case] Summary exactly at `summary_max_chars` passes through unmarked; one char over appends truncation marker.
- [Hidden Failure] Mid-board `CodexAgentError` with `stop_on_error=true` halts and preserves completed prefix; with false, marks step failed and continues.
- [Hidden Failure] Retry succeeds on second attempt → step completed once, no duplicate result entries.
- [Silent Failure] Off-by-one window: task 90 with `window=10` sees indices 80–89, never 79 or 90; assert exact ID labels.
- [Silent Failure] `head-tail` split keeps head and tail evenly (limit//2 each side) rather than dropping the tail.
- [Silent Failure] Thread IDs are unique per step; no agent resumes another task's thread.
- [Hidden Assumption] Task text containing `{{...}}` template braces is never interpolated into the prompt template.
- [Hidden Assumption] Runner receives verified grant and never calls admit/verify endpoints itself (assert via fake that network hits = 0 during `execute_task_board`).

## 11. Dependencies

- Pinned `vidbyte-sdk` `CodexHarnessAgent` + `CodexRunInput.text` + `CodexAgentSettings`/`CodexClientSettings`/`CodexHarnessAgentSettings` (same imports as persistence).
- Backend `X402_CATALOG`, `RuntimeAdmissionService`, gatekeeper `RouteRule` projection; no new packages.
- CLI `click`, `pydantic`, `vidbyte` SDK (lazy import inside session so `--help` stays offline).

## 12. Rollout

1. Land backend catalog + route + host guard; verify `GET /api/x402/runtime` lists task-board and unmounted-discovery check passes.
2. Land CLI behind the same admission price (2c); `runtime list` shows it with no hard-coded price.
3. Smoke locally on 3 tasks with `window=2` on codex host; confirm stdout carries only final `TaskBoardResult`, diagnostics on stderr.
4. Run `python scripts/run_ci.py` (CLI) and `python lint/run.py` (backend) before PR.

## 13. Open Questions

- Q1: Flat 2c vs 25c? Chosen 2c to match persistence/ensemble (local execution, caller-owned model cost). Confirm with pricing owner.
- Q2: Should `window` max stay 25? 25×8000 chars risks >100k prompt; current cap plus truncation bounds it, but a token-budget setting may follow.
- Q3: Future LLM summarizer: keep deterministic v1; add `summary-mode=llm` only with its own admission/metering review.

## 14. Alternatives Considered

- A1: One long-lived agent with thread resume across tasks. Rejected because thread compaction and hidden provider state make the window non-deterministic; fresh-per-task keeps the summary block the sole channel.
- A2: Raw history passthrough without summarization. Rejected per requirement that context is always a summary; raw passthrough breaks the 100-task budget and leaks unbounded prior output.
- A3: Parallel fan-out of tasks. Rejected for v1 because window semantics require total order; parallelism would need DAG + deterministic merge, deferred to a later primitive.
- A4: Backend-executed board with Inngest. Rejected because runtime-primitive policy keeps execution caller-local; backend only admits and verifies.
