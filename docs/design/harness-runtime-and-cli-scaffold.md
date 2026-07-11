# Design Doc: Harness Runtime Boilerplate + Universal Vidbyte CLI Scaffold

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-11
**Last Updated:** 2026-07-11

---

## 1. Overview

This change lays the structural foundation for Vidbyte product harnesses — closed-source, backend-executed agent workflows that users trigger from their own machines. It creates the shared harness runtime skeleton inside `vidbyte/backend` (services, orchestrator, public API routes, run queue, background worker — all boilerplate, no agent logic), scaffolds the first harness (`software_engineering`) as stubbed stages, and bootstraps a brand-new universal `vidbyte-cli` repository (TypeScript, published-ready layout) that will be the client for auth, harness runs, and future API surfaces. The existing local `vidbyte-cli` folder (whose remote is already `cerredz/Vidbyte-Skills`) is renamed to `vidbyte-skills` so folder names match their repos.

---

## 2. Goals & Non-Goals

### Goals
- Establish the canonical folder/module layout for **all** future harnesses under `backend/services/harnesses/`, with a shared runtime (base contract, registry, run context, events, workspace, runner, worker).
- Scaffold the first harness, `software_engineering`, as boilerplate: typed inputs/outputs, staged workflow (`plan → implement → finalize`), prompts package — every stage a clearly-marked stub.
- Expose the harness run lifecycle through the existing public API-key surface: `POST /harness/run`, `GET /harness/get/{run_id}`, `GET /harness/list`, following the exact route → orchestrator → service → queries layering used by `/project/*`.
- Persist runs in a new `harness_runs` Mongo collection acting as the run queue (status machine: `queued → running → completed | failed`).
- Start an in-process background worker (asyncio task, concurrency-capped) from `app.py` startup hooks, following the `tutor_worker_runtime` precedent, gated behind a `HARNESS_RUNTIME_ENABLED` env flag (default **off**).
- Rename local folder `vidbyte-repos/vidbyte-cli` → `vidbyte-repos/vidbyte-skills` (filesystem only; its git remote already points at `Vidbyte-Skills`).
- Create a new `vidbyte-repos/vidbyte-cli` folder, `git init` on `main`, remote `https://github.com/cerredz/Vidbyte-cli.git` (repo exists, empty), and scaffold a scalable TypeScript CLI: command modules (auth, harness, config, setup), API client layer, credential/config stores, output/error layers — all stubs.
- Push the CLI scaffold as the initial commit(s) to `main` of `Vidbyte-cli` (an empty repo cannot receive a PR).

### Non-Goals
- **No harness intelligence.** No LLM calls, no SDK wiring, no git clone/push/PR logic, no prompt content. Stubs raise `HarnessNotImplementedError` (runs flow `queued → running → failed` with an honest message, proving the pipeline end-to-end).
- No billing/token-metering wiring (the envelope carries `token_stats`/`pricing` fields; population is future work).
- No GitHub App / OAuth connect flow — `workspace.py` and `vidbyte connect github` are stubs.
- No MCP tool for harness runs (CLI-first per prior design discussion; MCP is a follow-up).
- No server-side execution of user code, and nothing in this change may ever shell out to user-controlled commands (standing invariant from the architecture discussion).
- No tests (per `/design-doc-no-tests`), no dashboard/frontend, no changes to `vidbyte-harnesses` (internal reference repo) or `vidbyte-sdk`.
- No npm publish of the CLI; the `vidbyte` bin-name collision with `vidbyte-skills` is resolved at publish time, not now (see Open Questions).

---

## 3. Background & Context

- **Why now:** an extended design conversation (Codex session + this session) converged on the v1 architecture: harnesses are closed-source and run *entirely on the Vidbyte backend* (Render); the CLI submits a run referencing the user's GitHub repo + SHA, the backend clones, edits, pushes a branch/draft PR; all LLM calls originate server-side and are billed to the user's Vidbyte API key. This PR builds the *skeleton* of that system so implementation can proceed incrementally.
- **Current state:** the backend has a mature public API-key platform (`/project/*`, `/roadmap/*`, `/quiz/*`) with auth middleware, permissions registry, response envelope, and orchestrator DI — but zero harness concepts. There is one precedent for in-process background workers (`routes/workers/tutor_worker_runtime.py`, started in `app.py` `startup_event`).
- **Repo facts verified:** local `vidbyte-cli` folder tracks `origin https://github.com/cerredz/Vidbyte-Skills` and its `package.json` is already named `vidbyte-skills` — the folder rename is pure alignment. `cerredz/Vidbyte-cli` exists on GitHub, is public and empty. Local `vidbyte` checkout is on a feature branch; the worktree must branch from `origin/main`.
- **Constraints:** Render hosts the backend as one long-running service — the worker must be in-process, deploys kill in-flight runs (handled: startup reaper marks orphaned `running` rows failed), and concurrency must be capped.

---

## 4. Requirements

### Functional Requirements
1. `POST /harness/run` (API-key auth, permission `harnesses:write`) accepts `{harness, task, repo:{url, sha, branch?}}`, validates the harness name against the registry, inserts a `queued` run owned by `request.state.user_id`, and returns the run id + status in the standard `PublicApiResponseFactory` envelope.
2. `GET /harness/get/{run_id}` (permission `harnesses:read`) returns the run's status, event log, and result fields — only to its owner; a non-owner or unknown id gets the standard 404 envelope.
3. `GET /harness/list` (permission `harnesses:read`) returns the caller's runs, paginated with `PublicApiListPaginationDto` semantics (limit/page), newest first.
4. A registry (`services/harnesses/registry.py`) maps harness names → harness classes; `software-engineering` is the sole entry. Unknown names are rejected at the route with a 400 envelope.
5. A background worker starts on app startup **only when** `HARNESS_RUNTIME_ENABLED=true`: it atomically claims the oldest `queued` run (`find_one_and_update` → `running`), builds a `HarnessRunContext`, invokes the harness's `run()`, and transitions the run to `completed`/`failed`, appending timestamped events at each transition.
6. The `software_engineering` harness class exists with staged stubs (`plan`, `implement`, `finalize`) that raise `HarnessNotImplementedError`; a claimed run therefore ends `failed` with event `"harness not implemented"` — demonstrating the full queue → claim → execute → persist pipeline.
7. On startup (flag on), any run left in `running` (orphaned by a deploy) is marked `failed` with a "restarted during execution — please retry" event before the worker begins polling.
8. Router registration, worker startup, and worker shutdown are all gated by `HARNESS_RUNTIME_ENABLED` (default false) so merging is a production no-op.
9. Local folder `vidbyte-cli` is renamed `vidbyte-skills`; its git remote and contents are untouched.
10. A new `vidbyte-cli` folder is initialized as a git repo on `main` with remote `origin → https://github.com/cerredz/Vidbyte-cli.git`, containing the full CLI scaffold, and pushed.
11. The CLI scaffold parses and dispatches these commands (each printing a clear "not implemented yet" message with exit code 1, except `--help`/`--version` which work fully): `vidbyte login`, `vidbyte logout`, `vidbyte whoami`, `vidbyte connect github`, `vidbyte harness run <name> --task <task>`, `vidbyte harness status <run_id>`, `vidbyte harness list`, `vidbyte config get|set`, `vidbyte doctor`.
12. The CLI's API client layer (`src/lib/api/`) centralizes base URL (`VIDBYTE_API_URL` env override, default `https://api.vidbyte.ai`), API-key header injection from the credential store, and typed envelope parsing — commands never call `fetch` directly.
13. CLI credentials/config live under `~/.vidbyte/` (`credentials.json` chmod-equivalent guidance, `config.json`); paths are resolved in one module (`src/lib/config/paths.ts`).

### Non-Functional Requirements
- **Performance:** run creation is a single insert (< 50ms typical); worker poll interval 3s; worker concurrency cap = 1 (constant, adjustable later).
- **Scalability:** queue-in-Mongo + atomic claim means moving the worker to a Render Background Worker later requires zero schema or API changes.
- **Security:** all `/harness/*` routes are API-key-only via `_API_KEY_ONLY_ROUTE_PERMISSIONS`; runs are strictly owner-scoped in every query; no user-controlled shell execution anywhere; CLI never logs the API key.
- **Observability:** worker and orchestrator log via the module logger with a `[harness]`-prefixed, key=value style matching `[public_api.project.route.create]` conventions; every status transition appends a persisted run event.
- **Reliability:** worker loop catches all exceptions per-run (a poisoned run fails; the loop survives); startup reaper handles deploy interruptions; graceful shutdown cancels the poll task.

---

## 5. High-Level Design

Two workstreams. **Backend (vidbyte repo, one PR):** a new `services/harnesses/` package holds everything harness-shaped — a `BaseHarness` abstract contract, a name→class `registry`, a `HarnessRunContext` carrying per-run state, an `events` emitter that persists progress, a `GitWorkspace` stub (future clone/branch/PR seam), a `HarnessRunner` that executes one claimed run, and a `worker` loop that polls the queue. The public surface reuses the platform exactly as `/project/*` does: `routes/harness_public.py` (thin) → `orchestrators/routes/harnesses.py` (`PublicApiHarnessOrchestrator`) → `database/queries/harness_runs.py` (Mongo). DTOs/enums/errors slot into `lib/`. `app.py` registers the router and starts/stops the worker inside the existing startup/shutdown events, all behind `HARNESS_RUNTIME_ENABLED`.

```
CLI ──POST /harness/run──► routes/harness_public ─► orchestrator ─► queries.insert (queued)
                                                                        │  harness_runs (Mongo)
        worker loop (asyncio, in-process, flag-gated) ◄─ atomic claim ──┘
              └─► HarnessRunner ─► registry["software-engineering"] ─► stub stages
                        └─► status transitions + events persisted ─► GET /harness/get/{id}
```

**CLI (new repo, initial push):** a commander-based TypeScript ESM CLI with strict layering — `src/commands/` (one folder per command group, thin: parse → call service → render), `src/lib/` (api client, auth store, config, git introspection, output, errors), `src/types/` (envelope + resource types mirroring the backend DTOs). `bin/vidbyte.js` is a shim into `dist/`. The layout is deliberately over-provisioned for a v1 so future surfaces (billing, skills, MCP) land as new command folders + endpoint modules without restructuring.

Key decisions: (1) queue lives in Mongo (no Redis/Celery — matches "cheapest v1 on Render" decision); (2) worker is in-process and flag-gated (tutor precedent, zero new infra); (3) stubs fail loudly rather than fake success, so the pipeline is testable end-to-end the day stage one is implemented; (4) TypeScript/npm for the CLI (npx reach into Claude Code/Codex sessions, team's existing Node CLI experience) over Python/Typer.

---

## 6. Detailed Design

> Style note (applies to every new file): class-first design, one-line signatures, a 1–2 line comment under every signature, sparse inline comments, matching existing backend idioms (`from __future__ import annotations`, keyword-only args, module logger).

### 6.1 Harness enums

**File(s):** `backend/lib/enums/harness.py` (new), `backend/lib/enums/__init__.py` (modified), `backend/lib/enums/public_api.py` (modified)
**Type:** New + Modified

#### What it does
Defines the harness vocabulary: `HarnessName` (`SOFTWARE_ENGINEERING = "software-engineering"`), `HarnessRunStatus` (`QUEUED, RUNNING, COMPLETED, FAILED`), `HarnessRunEventType` (`STATUS, LOG, ERROR`). Adds `HARNESS = "harness"` to `PublicApiObject` and harness entries to `PublicApiErrorTitle`/`PublicApiMessage` (following wherever those enum members live today — `lib/enums/public_api.py`).

#### Interface / API
```python
class HarnessName(str, Enum):
    SOFTWARE_ENGINEERING = "software-engineering"

class HarnessRunStatus(str, Enum):
    QUEUED = "queued"; RUNNING = "running"; COMPLETED = "completed"; FAILED = "failed"
```

#### Logic / Algorithm
Pure declarations; re-export from `lib/enums/__init__.py` like existing enum modules.

#### Edge Cases & Error Handling
N/A — declarations only.

### 6.2 Harness DTOs

**File(s):** `backend/lib/dtos/harness.py` (new), `backend/lib/dtos/__init__.py` (modified)
**Type:** New + Modified

#### What it does
Pydantic v2 request/resource models for the public surface and internal run documents.

#### Interface / API
```python
class HarnessRepoRefDto(BaseModel): url: str; sha: str; branch: str | None = None
class HarnessRunCreateRequestDto(BaseModel): harness: str; task: str; repo: HarnessRepoRefDto
class HarnessRunEventDto(BaseModel): type: str; message: str; created_at: datetime
class HarnessRunResultDto(BaseModel): branch: str | None = None; pr_url: str | None = None; summary: str | None = None
class HarnessRunResourceDto(BaseModel): run_id: str; harness: str; status: str; task: str; repo: HarnessRepoRefDto; events: list[HarnessRunEventDto]; result: HarnessRunResultDto | None; created_at: datetime; updated_at: datetime
```

#### Logic / Algorithm
`HarnessRunCreateRequestDto` uses field validators for non-empty `task` (max length 10_000) and a plausible `repo.url` (https or ssh git URL) — validation only, no network.

#### Edge Cases & Error Handling
Pydantic validation errors surface as FastAPI 422s, consistent with existing public DTOs.

### 6.3 Harness errors

**File(s):** `backend/lib/errors/harness.py` (new), `backend/lib/errors/__init__.py` (modified)
**Type:** New + Modified

#### What it does
`HarnessError` (base), `HarnessNotFoundError` (unknown registry name), `HarnessNotImplementedError` (stub stages), `HarnessRunNotFoundError` (missing/foreign run id). Each carries `status_code`, `code`, `title`, `detail` mirroring `PublicApiPersistenceError`'s shape so routes can map them onto the envelope uniformly.

#### Edge Cases & Error Handling
This *is* the error surface; routes catch these explicitly before the generic 500 handler.

### 6.4 Run queries (Mongo)

**File(s):** `backend/database/queries/harness_runs.py`
**Type:** New file

#### What it does
All persistence for the `harness_runs` collection; the only module that touches it.

#### Interface / API
```python
async def insert_harness_run(db, *, user_id: str, harness: str, task: str, repo: dict) -> str
async def get_harness_run(db, *, run_id: str, user_id: str) -> dict | None
async def list_harness_runs(db, *, user_id: str, limit: int, page: int) -> tuple[list[dict], int]
async def claim_next_queued_run(db) -> dict | None
async def set_run_status(db, *, run_id: str, status: str, event_message: str) -> None
async def append_run_event(db, *, run_id: str, event_type: str, message: str) -> None
async def fail_orphaned_running_runs(db) -> int
```

#### Logic / Algorithm
1. `insert_harness_run` writes `{user_id, harness, task, repo, status: "queued", events: [status event], result: None, created_at, updated_at}` and returns the stringified `_id`.
2. `claim_next_queued_run` = `find_one_and_update(filter={"status": "queued"}, update={$set: {"status": "running", ...}}, sort=[("created_at", 1)], return_document=AFTER)` — atomic claim, the Mongo analogue of `SKIP LOCKED`.
3. `set_run_status`/`append_run_event` push `{type, message, created_at}` onto `events` and bump `updated_at`.
4. `fail_orphaned_running_runs` = `update_many(status=="running" → "failed")` with the restart event; returns count for logging.
5. All read paths filter by `user_id` (owner scoping is enforced here, not in callers).

#### Edge Cases & Error Handling
Invalid `ObjectId` strings return `None` (treated as not-found) rather than raising; concurrent claims are safe by construction of `find_one_and_update`.

### 6.5 Shared harness runtime

**File(s):** `backend/services/harnesses/__init__.py`, `base.py`, `context.py`, `events.py`, `registry.py`, `workspace.py`, `runner.py`, `worker.py`, `README.md`
**Type:** New files (9)

#### What it does
The reusable core every harness plugs into.

#### Interface / API
```python
# base.py
class BaseHarness(ABC):
    name: ClassVar[str]
    async def run(self, ctx: HarnessRunContext) -> HarnessRunResultDto: ...  # abstract

# context.py
@dataclass
class HarnessRunContext:  # run doc snapshot + db handle + event emitter + workspace
    run_id: str; user_id: str; task: str; repo: HarnessRepoRefDto
    events: RunEventEmitter; workspace: GitWorkspace

# events.py
class RunEventEmitter:
    async def status(self, message: str) -> None
    async def log(self, message: str) -> None
    async def error(self, message: str) -> None

# registry.py
HARNESS_REGISTRY: dict[str, type[BaseHarness]]
def get_harness_class(name: str) -> type[BaseHarness]   # raises HarnessNotFoundError

# workspace.py  (stubs — the future GitHub seam)
class GitWorkspace:
    async def clone_at_sha(self) -> Path            # raises HarnessNotImplementedError
    async def create_run_branch(self) -> str        # raises HarnessNotImplementedError
    async def push_and_open_draft_pr(self) -> str   # raises HarnessNotImplementedError
    async def cleanup(self) -> None                 # no-op safe to call always

# runner.py
class HarnessRunner:
    async def execute(self, run_doc: dict) -> None  # full lifecycle for one claimed run

# worker.py
def start_harness_worker() -> None        # creates the asyncio poll task (idempotent)
async def shutdown_harness_worker() -> None
```

#### Logic / Algorithm
`HarnessRunner.execute` (composed of small named methods per house style): resolve harness class from registry → build context (emitter bound to run_id, workspace from repo ref) → `await harness.run(ctx)` → on success `set_run_status(completed)` + persist result → on any exception `set_run_status(failed)` with the error message (truncated) → `workspace.cleanup()` in `finally`. `worker.start_harness_worker` spawns one `asyncio.Task` looping: `claim_next_queued_run` → if none, `sleep(POLL_INTERVAL_SECONDS)` → else `HarnessRunner().execute(run)`. Shutdown cancels the task and awaits it.

#### Edge Cases & Error Handling
Registry misses raise `HarnessNotFoundError` (also guarded at the route, so the worker hitting it means a deleted registry entry — run fails cleanly). The loop wraps each iteration in try/except so one bad run never kills the worker. Double `start_harness_worker` calls are no-ops (module-level task handle check).

### 6.6 Software-engineering harness (boilerplate)

**File(s):** `backend/services/harnesses/software_engineering/__init__.py`, `harness.py`, `workflow.py`, `models.py`, `prompts/__init__.py`, `README.md`
**Type:** New files (6)

#### What it does
The first product harness, structured for the real implementation but entirely stubbed.

#### Interface / API
```python
class SoftwareEngineeringHarness(BaseHarness):
    name = HarnessName.SOFTWARE_ENGINEERING.value
    async def run(self, ctx: HarnessRunContext) -> HarnessRunResultDto:
        # Orchestrates plan → implement → finalize; each stage is a stub today.
        plan = await self._plan(ctx)
        changes = await self._implement(ctx, plan)
        return await self._finalize(ctx, changes)
```
`workflow.py` holds the stage dataclasses (`PlanResult`, `ImplementResult`) and stage stubs; `models.py` holds harness-specific pydantic models; `prompts/__init__.py` is an empty package with a README pointer (prompt content is future work and stays out of git history until then — it's the closed-source payload).

#### Logic / Algorithm
Every private stage emits a status event (`await ctx.events.status("planning")`) then raises `HarnessNotImplementedError("software-engineering harness stages are not implemented yet")`. This ordering means a queued run today produces the event trail `queued → running → planning → failed(not implemented)` — the whole pipeline observable via `GET /harness/get/{id}`.

#### Edge Cases & Error Handling
None beyond the deliberate stub failure; the runner converts it to a failed run.

### 6.7 Public API orchestrator

**File(s):** `backend/orchestrators/routes/harnesses.py` (new), `backend/orchestrators/routes/__init__.py` (modified), `backend/lib/api/dependencies.py` (modified)
**Type:** New + Modified

#### What it does
`PublicApiHarnessOrchestrator` — create/get/list coordination between routes and queries, mirroring `PublicApiProjectOrchestrator`'s shape (keyword-only methods taking `user_id`, `db`).

#### Interface / API
```python
class PublicApiHarnessOrchestrator:
    async def create_run(self, *, user_id: str, payload: HarnessRunCreateRequestDto, db) -> HarnessRunResourceDto
    async def get_run(self, *, user_id: str, run_id: str, db) -> HarnessRunResourceDto
    async def list_runs(self, *, user_id: str, pagination: PublicApiListPaginationDto, db) -> tuple[list[HarnessRunResourceDto], PublicApiPageMetadataDto]

def get_harness_orchestrator() -> PublicApiHarnessOrchestrator  # in lib/api/dependencies.py
```

#### Logic / Algorithm
`create_run`: validate name via `get_harness_class` (raises `HarnessNotFoundError` → 400) → insert → fetch → serialize to DTO. `get_run`: query (owner-scoped) → `HarnessRunNotFoundError` if `None`. `list_runs`: paginated query → DTOs + page metadata. A private `_to_resource_dto(doc)` handles Mongo→DTO mapping in one place.

#### Edge Cases & Error Handling
Raises the typed errors from 6.3; never returns another user's run (scoping lives in the query layer).

### 6.8 Public routes

**File(s):** `backend/routes/harness_public.py`
**Type:** New file

#### What it does
Thin FastAPI router, `prefix="/harness"`, tags `["public-harness"]`, mirroring `project_public.py`: try orchestrator call → `PublicApiResponseFactory.success(...)`; catch typed harness errors → `error_response(...)`; catch-all → logged 500 envelope with `[public_api.harness.route.*]` log prefixes.

#### Interface / API
See Section 8.

#### Edge Cases & Error Handling
Unknown harness → 400; missing/foreign run → 404; unexpected → 500 envelope; all via the factory so error shapes match the rest of the platform.

### 6.9 Worker runtime wrapper + app wiring

**File(s):** `backend/routes/workers/harness_worker_runtime.py` (new), `backend/app.py` (modified), `backend/.env.example` (modified)
**Type:** New + Modified

#### What it does
`start_harness_runtime()` / `shutdown_harness_runtime()` following `tutor_worker_runtime.py`'s pattern: read `HARNESS_RUNTIME_ENABLED` (default `"false"`), no-op when off; when on, run the orphan reaper then `start_harness_worker()`. `app.py`: import router + runtime; `include_router(harness_public_router)` gated by the same flag check at import-registration time; add start/shutdown calls inside the existing `startup_event`/`shutdown` handlers. `.env.example` documents `HARNESS_RUNTIME_ENABLED=false`.

#### Edge Cases & Error Handling
Flag off = merged code is dead weight only; flag on in a deploy with no Mongo reachable fails at startup loudly (same behavior as existing DB-dependent startup).

### 6.10 API-key permissions registry

**File(s):** `backend/middleware/api_platform.py`
**Type:** Modified

#### What it does
Adds to `_API_KEY_ONLY_ROUTE_PERMISSIONS`: `("/harness/run", "harnesses:write")`, `("/harness/get", "harnesses:read")`, `("/harness/list", "harnesses:read")`. This routes them through existing API-key auth + permission checks with zero new middleware.

#### Edge Cases & Error Handling
Prefix matching is the module's existing behavior; `/harness/get/{id}` matches the `/harness/get` prefix.

### 6.11 Universal Vidbyte CLI scaffold (new repo)

**File(s):** entire `vidbyte-repos/vidbyte-cli/` tree (new repo)
**Type:** New repository

#### What it does
A commander-based TypeScript ESM CLI whose v1 job is harness runs + auth, structured so every future surface is additive.

```text
vidbyte-cli/
├── package.json              # name "vidbyte-cli", bin { "vidbyte": "./bin/vidbyte.js" }, engines node>=18
├── tsconfig.json             # strict, NodeNext, outDir dist
├── .gitignore                # node_modules, dist, .env
├── .env.example              # VIDBYTE_API_URL, VIDBYTE_API_KEY (dev override)
├── LICENSE                   # MIT (matches sibling repos)
├── README.md                 # install, quickstart, command reference, architecture map
├── bin/
│   └── vidbyte.js            # #!/usr/bin/env node shim → ../dist/index.js
├── src/
│   ├── index.ts              # program bootstrap: build commander program, register groups, global error trap
│   ├── commands/
│   │   ├── index.ts          # registerAllCommands(program) — single registration point
│   │   ├── auth/             # login.ts, logout.ts, whoami.ts, connectGithub.ts
│   │   ├── harness/          # run.ts, status.ts, list.ts
│   │   ├── config/           # get.ts, set.ts
│   │   └── setup/            # doctor.ts (env/auth/connectivity checks — stub)
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts     # ApiClient class: base URL, key header, envelope parse, typed errors
│   │   │   └── endpoints/
│   │   │       ├── harness.ts# createRun/getRun/listRuns (typed, stubbed against future routes)
│   │   │       └── auth.ts   # whoami (stub)
│   │   ├── auth/
│   │   │   └── credentials.ts# CredentialStore: read/write ~/.vidbyte/credentials.json
│   │   ├── config/
│   │   │   ├── config.ts     # ConfigStore: ~/.vidbyte/config.json get/set
│   │   │   └── paths.ts      # single source for ~/.vidbyte paths
│   │   ├── git/
│   │   │   └── repoInfo.ts   # RepoInspector: origin URL, HEAD sha, branch, dirty check (stub)
│   │   ├── output/
│   │   │   ├── logger.ts     # leveled, color-aware, --json mode aware
│   │   │   └── render.ts     # tables/status rendering helpers
│   │   └── errors/
│   │       └── cliError.ts   # CliError with exitCode; central handler maps to process.exit
│   └── types/
│       └── api.ts            # envelope + HarnessRun types mirroring backend DTOs
├── docs/
│   └── architecture.md       # the layering rules above, for contributors
└── scripts/
    └── smoke.js              # runs `vidbyte --help` against dist as a build sanity check
```

#### Logic / Algorithm
Layering rule (recorded in `docs/architecture.md`): commands → endpoints → client; commands never touch `fetch`, stores, or `process.exit` directly (they throw `CliError`; `index.ts` owns the trap). Every command handler is a small class (`LoginCommand.execute()` etc.) per house style. Stub behavior: parse args fully, then `throw new CliError("'vidbyte login' is not implemented yet", 1)`.

#### Edge Cases & Error Handling
Missing credentials file → clean "run `vidbyte login` first" message (once implemented); unknown command → commander's help + exit 1; `--json` flag reserved on the program for machine-readable output later.

### 6.12 Folder rename + repo bootstrap (procedure, not code)

**Type:** Filesystem/git operations

1. Preconditions (verify before acting): no process holding `vidbyte-cli`; `git -C vidbyte-cli status` clean enough to move (moving is safe regardless — the `.git` dir moves with it).
2. `Rename-Item vidbyte-cli vidbyte-skills` — remote already `Vidbyte-Skills`, so nothing else changes.
3. `mkdir vidbyte-cli; git init -b main; git remote add origin https://github.com/cerredz/Vidbyte-cli.git`.
4. Scaffold files, `npm install` (commander + dev deps: typescript, @types/node), `npm run build` + `node scripts/smoke.js` to verify, commit(s), `git push -u origin main`.

#### Edge Cases & Error Handling
If the rename target `vidbyte-skills` already exists, abort and report (it does not today). Empty GitHub repo means push-to-main is the only bootstrap path; confirmed empty.

---

## 7. Data Model Changes

### 7.1 `harness_runs` (MongoDB collection)

**Change type:** New

```javascript
{
  _id: ObjectId,
  user_id: "string",              // owner; every query filters on this
  harness: "software-engineering",
  task: "string",
  repo: { url: "string", sha: "string", branch: "string|null" },
  status: "queued|running|completed|failed",
  events: [ { type: "status|log|error", message: "string", created_at: ISODate } ],
  result: { branch: "string|null", pr_url: "string|null", summary: "string|null" } | null,
  created_at: ISODate,
  updated_at: ISODate
}
```

**Migration strategy:**
- Forward: none needed — Mongo collections are created on first insert. (Index creation — `{status: 1, created_at: 1}` for claims, `{user_id: 1, created_at: -1}` for lists — is documented in the queries module docstring as a deploy note; no automatic index management exists in this codebase today.)
- Rollback: drop the collection; no other data references it.

---

## 8. API Changes

### 8.1 POST /harness/run

**Change type:** New (API-key auth, permission `harnesses:write`, registered only when `HARNESS_RUNTIME_ENABLED=true`)

**Request:**
```json
{
  "harness": "string - registry name, e.g. software-engineering",
  "task": "string - what the harness should do",
  "repo": { "url": "string - git URL", "sha": "string - commit to run against", "branch": "string|null" }
}
```

**Response:** standard `PublicApiResponseFactory` success envelope; `data` = `HarnessRunResourceDto` (run_id, status "queued", events, timestamps).

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Unknown harness name |
| 401 | Missing/invalid API key (middleware) |
| 403 | Key lacks `harnesses:write` (middleware) |
| 422 | DTO validation failure |
| 500 | Persistence failure (envelope) |

### 8.2 GET /harness/get/{run_id}

**Change type:** New (permission `harnesses:read`)

**Response:** success envelope, `data` = full `HarnessRunResourceDto` including `events` and `result`.

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Run not found or owned by another user |
| 401/403 | Auth/permission (middleware) |
| 500 | Unexpected (envelope) |

### 8.3 GET /harness/list

**Change type:** New (permission `harnesses:read`; query params `limit` 1–100 default 100, `page` ≥1 default 1)

**Response:** success envelope, `data` = array of `HarnessRunResourceDto` (events omitted for brevity — summary fields only), plus standard `pagination` metadata.

**Error cases:** as 8.2 minus 404.

---

## 9. File Change Manifest

**vidbyte repo (backend):**

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/harness-runtime-and-cli-scaffold.md` | This design doc |
| CREATE | `backend/lib/enums/harness.py` | Harness name/status/event enums |
| MODIFY | `backend/lib/enums/__init__.py` | Re-export harness enums |
| MODIFY | `backend/lib/enums/public_api.py` | Add HARNESS object type + messages/titles |
| CREATE | `backend/lib/dtos/harness.py` | Request/resource DTOs |
| MODIFY | `backend/lib/dtos/__init__.py` | Re-export harness DTOs |
| CREATE | `backend/lib/errors/harness.py` | Typed harness errors |
| MODIFY | `backend/lib/errors/__init__.py` | Re-export harness errors |
| CREATE | `backend/database/queries/harness_runs.py` | Run queue persistence + atomic claim |
| CREATE | `backend/services/harnesses/__init__.py` | Package init |
| CREATE | `backend/services/harnesses/README.md` | Runtime architecture guide |
| CREATE | `backend/services/harnesses/base.py` | BaseHarness contract |
| CREATE | `backend/services/harnesses/context.py` | HarnessRunContext |
| CREATE | `backend/services/harnesses/events.py` | RunEventEmitter |
| CREATE | `backend/services/harnesses/registry.py` | Name → class registry |
| CREATE | `backend/services/harnesses/workspace.py` | GitWorkspace stubs (future GitHub seam) |
| CREATE | `backend/services/harnesses/runner.py` | HarnessRunner lifecycle |
| CREATE | `backend/services/harnesses/worker.py` | Poll loop + start/shutdown |
| CREATE | `backend/services/harnesses/software_engineering/__init__.py` | Package init |
| CREATE | `backend/services/harnesses/software_engineering/README.md` | Harness-specific guide |
| CREATE | `backend/services/harnesses/software_engineering/harness.py` | SoftwareEngineeringHarness (stubbed stages) |
| CREATE | `backend/services/harnesses/software_engineering/workflow.py` | Stage models + stubs |
| CREATE | `backend/services/harnesses/software_engineering/models.py` | Harness-specific pydantic models |
| CREATE | `backend/services/harnesses/software_engineering/prompts/__init__.py` | Prompts package placeholder |
| CREATE | `backend/orchestrators/routes/harnesses.py` | PublicApiHarnessOrchestrator |
| MODIFY | `backend/orchestrators/routes/__init__.py` | Export orchestrator |
| MODIFY | `backend/lib/api/dependencies.py` | get_harness_orchestrator DI |
| CREATE | `backend/routes/harness_public.py` | /harness/run, /harness/get, /harness/list |
| CREATE | `backend/routes/workers/harness_worker_runtime.py` | Flag-gated start/shutdown wrapper |
| MODIFY | `backend/middleware/api_platform.py` | Register harness API-key permissions |
| MODIFY | `backend/app.py` | Router + worker wiring (flag-gated) |
| MODIFY | `backend/.env.example` | Document HARNESS_RUNTIME_ENABLED |

**Filesystem / new CLI repo:**

| Action | Path | Reason |
|--------|------|--------|
| RENAME | `vidbyte-repos/vidbyte-cli` → `vidbyte-repos/vidbyte-skills` | Align folder with its actual remote (Vidbyte-Skills) |
| CREATE | `vidbyte-repos/vidbyte-cli/` (~28 files per §6.11 tree) | New universal CLI repo, pushed to cerredz/Vidbyte-cli `main` |

Totals: vidbyte repo — 24 created, 8 modified, 0 deleted. New CLI repo — ~28 files created. One rename.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| motor (existing) | already in requirements | harness_runs persistence | None — no new backend deps |
| commander | ^12 (new repo only) | CLI framework | Low — ubiquitous, zero transitive weight |
| typescript / @types/node | ^5 / ^20 (dev, new repo) | Build | Low |
| github.com/cerredz/Vidbyte-cli | empty repo, main | CLI home | Push access assumed (gh authed as owner) |

No new external services. No SDK dependency yet (deliberate — enters with the first real stage implementation).

---

## 11. Rollout & Deployment

- **Feature flag:** `HARNESS_RUNTIME_ENABLED` (default false) gates router registration, worker startup, and orphan reaping. Merging + deploying is a production no-op.
- **Breaking changes:** none. No existing routes, schemas, or middleware behavior change; `api_platform.py` additions only affect the new paths.
- **Deployment order:** backend PR merges whenever; CLI repo push is independent; nothing depends on ordering.
- **Rollback:** flip the flag off (or revert the PR); drop `harness_runs` if desired.
- **CLI publish:** explicitly deferred; repo is pushed but not published to npm, so the `vidbyte` bin collision with the `vidbyte-skills` package cannot bite anyone yet.

---

## 12. Open Questions

- [ ] **npm bin collision:** `vidbyte-skills`' package.json maps the `vidbyte` bin to its installer. Before the new CLI publishes to npm, that mapping should be removed/renamed in Vidbyte-Skills (follow-up PR there). Confirm you want the universal CLI to own the `vidbyte` command (assumed yes).
- [ ] **npm package name:** `vidbyte-cli` vs `vidbyte` vs scoped `@vidbyte/cli` — decide at publish time; scaffold uses `vidbyte-cli`.
- [ ] **API base URL:** scaffold defaults to `https://api.vidbyte.ai` — confirm the production API host before the CLI makes real calls.
- [ ] **Run event streaming:** v1 is poll-based (`GET /harness/get/{id}`); SSE is a future decision, noted in the routes module docstring.

---

## 13. Alternatives Considered

### Alternative 1: Harness code in `vidbyte-sdk` or `vidbyte-harnesses`
- What: develop product harnesses in the public SDK repo or the existing internal harnesses repo.
- Why rejected: settled in the preceding design discussions — harnesses are closed-source product code and the main backend is their source of truth; the SDK stays primitives-only (it enters later as a dependency); `vidbyte-harnesses` is an internal reference project.

### Alternative 2: Redis/Celery (or Render Background Worker) for the run queue
- What: a real task queue instead of a Mongo collection + in-process poller.
- Why rejected for v1: the "cheapest thing on Render" decision — a status-machine collection with `find_one_and_update` claims gives atomicity with zero new infrastructure, and the schema/API are unchanged if the worker later moves to a separate Render service.

### Alternative 3: Python (Typer) CLI
- What: match the backend/SDK language.
- Why rejected: npm/npx distribution is the lowest-friction path into Claude Code/Codex user environments (their own precedent: Claude Code is an npm package), and the team already ships a Node CLI (vidbyte-skills). pipx is a heavier ask for JS-first users than npx is for Python-first users.

### Alternative 4: oclif instead of commander
- What: batteries-included CLI framework with plugins/autoupdate.
- Why rejected: heavy for a v1 whose commands are stubs; commander + the documented layering delivers the same scalability without framework lock-in. Revisit if a plugin ecosystem becomes a requirement.

### Alternative 5: Fake-success stubs
- What: have stub stages return canned results so runs reach `completed`.
- Why rejected: dishonest pipelines hide integration bugs; a loud `failed (not implemented)` run proves queue, claim, events, and status transitions truthfully.
