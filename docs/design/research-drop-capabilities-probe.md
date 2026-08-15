# Design Doc: Drop the research capabilities probe and the export command surface

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-14
**Last Updated:** 2026-08-14

---

## 1. Overview

Every research read in `ApiResearchGateway` calls a private `_require_read_contract()` helper
before it issues its own request. That helper fetches `GET /research/capabilities`, a route the
Vidbyte backend has never implemented. The 404 is translated into
`API_PROTOCOL_ERROR: "This Vidbyte API does not expose the research capability contract."`, so
`research status`, `research watch`, `research resume`, and every list command fail with a
misleading version error before touching the endpoint they actually need. This change deletes the
probe, the capabilities concept, and the export command surface it was the gatekeeper for, so that
looking up a run only looks up that run.

---

## 2. Goals & Non-Goals

### Goals

- Remove `_require_read_contract()` and every call to it, so no read makes a second request.
- Remove the `ResearchCapabilities` concept end to end: domain model, wire DTO, gateway method,
  application query, Click command, presenter, and route constant.
- Remove the export command surface (`research export artifact|thread|portfolio|status`), the
  `ResearchExportService`, the export DTOs, and the export route constants. There is no backend
  export API, and the capability check existed only to guard it.
- Leave `research status`, `watch`, `resume`, and the list commands issuing exactly the HTTP
  requests they name, and no others.
- Keep the local poll interval exactly as it is: a client-side constant, not server-supplied.
- Keep `python scripts/run_ci.py` green.

### Non-Goals

- Adding a `/research/capabilities` backend route. There is no consumer left for it.
- Adding an export API, in this repo or the backend.
- Fixing the missing `/api/v1` prefix on `ResearchRoutes`. That is a separate, already-identified
  defect and is deliberately out of scope (see §12).
- Making `research runs list`, `threads list`, `sources list`, or `artifacts list` succeed. Their
  backend routes do not exist; after this change they fail on their own 404 instead of on the
  probe's version error. That is the intended outcome, not a regression.
- Porting the research feature onto `main`. See §11.
- Rewriting `docs/design/python-cli-research-harness-program.md`, the 1650-line program doc whose
  §§ describing export and capabilities become stale. Recorded as a follow-up in §12.

---

## 3. Background & Context

The research feature was built against a forward-looking guess at the public API. `routes.py` says
so explicitly in its own header: *"Read, capability, and export paths are explicitly assumed forward
contracts until their backend PR lands."* Only the mutation paths were confirmed.

The backend branch `feat/research-api-prefix-and-read-routes` in the `vidbyte` repo has since landed
its read routes, and the confirmed surface is six routes:

```
POST /api/v1/research/run
POST /api/v1/research/threads/{encrypted_id}/run
POST /api/v1/research/runs/{run_id}/continue
GET  /api/v1/research/runs/{run_id}
GET  /api/v1/research/portfolio
GET  /api/v1/research/threads/{encrypted_id}
```

There is no `/capabilities` and no `/exports`. The assumed contracts did not land, and the CLI's
handling of their absence is not a graceful degrade — it is a hard failure on every read path.

The probe was built to do two jobs, and neither is real:

1. **Detect an old server.** There is no old server to detect. The probe asks the one deployed
   backend a question it has never been able to answer, so the "your API is too old" guard is a
   permanent false positive.
2. **Validate export targets.** `ApiResearchGateway.export()` checks `request.provider` against
   `capabilities.export_providers` before POSTing to `/research/exports`, which also 404s. The check
   guards a call that cannot succeed.

**Branch context.** The research feature exists only on `feat/research-api-wiring`. `main` has no
`src/vidbyte_cli/features/` directory at all — the stack `feat/cli-http-operation-platform` →
`research-domain-application` → `research-command-surface` → `research-api-wiring` (PRs #7–#10) shows
every PR as MERGED, but each merged into its predecessor's branch, and the root of the chain (PR #6)
was CLOSED rather than merged. This is the stacked-PR orphan pattern the field guide's
"Branch from the PR that is actually alive" rule describes, recurring a third time.

The work cannot be cherry-picked to `main` either: `main` rewrote the platform layer more compactly
in PR #11, and the modules this feature imports do not exist there (`lib/polling/poller.py`,
`lib/runtime/signals.py`, `lib/runtime/clock.py`, `lib/api/response.py`, `lib/api/problem.py`).
`main`'s `ApiClient.get(path, model)` has no `shape=` or `idempotency_key` parameter and no
`request()` method.

This PR therefore targets `feat/research-api-wiring` by explicit decision, accepting that it does not
reach `main`. Its value is that when the research feature is eventually ported forward, the dead
capability and export surface does not come with it.

---

## 4. Requirements

### Functional Requirements

1. `ApiResearchGateway.get_run` issues exactly one HTTP request: `GET` on the run path.
2. `ApiResearchGateway.list_runs`, `list_threads`, `list_sources`, `list_artifacts`, and
   `get_artifact` each issue exactly one HTTP request on their own path.
3. No code path in `src/` requests `/research/capabilities`.
4. No code path in `src/` requests `/research/exports` or `/research/exports/{id}`.
5. `research resume` performs its resumability read and then its continue POST, with no other
   request in between.
6. `research capabilities` is no longer a registered Click command.
7. `research export` and its four subcommands are no longer registered Click commands.
8. A 404 from a research read surfaces as the mapper's own
   `OPERATION_FAILED: "The requested Vidbyte resource was not found."`, not as
   `API_PROTOCOL_ERROR`.
9. `ResearchWatcher` continues to poll `get_run` until terminal, using the client-side
   `PollOptions.interval_seconds` default, and continues to return `None` from
   `ResearchRunTarget.suggested_delay`.
10. `scripts/smoke.py` enumerates only commands that still exist.

### Non-Functional Requirements

- **Performance:** removes one HTTP round trip per read command, and one per poll tick during
  `watch`. On a 10-minute watch at the 2.0s default interval that is ~300 requests eliminated.
- **Scalability:** N/A — this is a client CLI with no shared state and no datastore.
- **Security:** no change to the credential path. Deleting `ApiResearchExportRequest` removes the
  only DTO carrying a third-party `provider` identifier.
- **Observability:** error messages become more accurate; a missing endpoint now reports itself
  rather than being reattributed to an API version mismatch.
- **Reliability:** one missing endpoint can no longer take down the entire research command set.
  Failures become local to the command that caused them.
- **Style:** deletions remove two bare `CliError(...)` constructions and one `usage_error(...)` call,
  both of which the field guide's `typed-failures.md` rules prohibit. Net movement toward the
  house style, with no new failure classes required.

---

## 5. High-Level Design

The change is a pure deletion across five layers of the research feature plus two call sites outside
it. Nothing is replaced, no abstraction is introduced, and no behavior is added. The design decision
is that the capability concept has no surviving consumer once export goes, so it is removed rather
than made fail-soft.

The alternative — catching the probe's 404 and continuing with an empty `ResearchCapabilities` — was
rejected because it keeps a per-command round trip whose result nothing reads (see §13).

Data flow before, for `research status`:

```
status cmd -> ResearchQueryService.status -> ApiResearchGateway.get_run
                                                |
                                                +-> _require_read_contract()
                                                |     -> GET /research/capabilities  [404]
                                                |     -> API_PROTOCOL_ERROR  (command dies)
                                                |
                                                +-> GET /research/runs/{id}   (never reached)
```

After:

```
status cmd -> ResearchQueryService.status -> ApiResearchGateway.get_run
                                                |
                                                +-> GET /research/runs/{id}
```

Layers touched:

- **domain** — drop `ResearchCapabilities`, `ExportScope`, `ResearchExportRequest`,
  `ResearchExport` from `models.py`; drop three methods from the `ResearchGateway` Protocol.
- **application** — drop `ResearchQueryService.capabilities`; delete `ResearchExportService`.
- **infrastructure** — drop the probe, the two version-error raisers, the capability cache field,
  the export methods, the export/capability route constants, and three wire DTOs.
- **commands** — delete `exports.py`; drop `ResearchCapabilitiesCommand`; simplify the registrar.
- **presentation** — drop `ResearchPresenter.capabilities` and `.export`.
- **runtime wiring** — drop `ApplicationContext.research_export_service()` and its cache field.
- **scripts** — drop five now-invalid smoke cases.

---

## 6. Detailed Design

### 6.1 ApiResearchGateway

**File(s):** `src/vidbyte_cli/features/research/infrastructure/api_gateway.py`
**Type:** Modified

#### What it does

Implements `ResearchGateway` over the Vidbyte public API. After this change it holds only the six
methods that map to real backend routes, plus the three read/list methods whose routes are assumed
but which now fail honestly.

#### Interface / API

```python
class ApiResearchGateway(ResearchGateway):
    def __init__(self, client: ApiClient, routes: ResearchRoutes | None = None) -> None: ...
    def start(self, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted: ...
    def add(
        self, thread_id: str, request: ResearchRunRequest, idempotency_key: str
    ) -> ResearchRunAccepted: ...
    def resume(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted: ...
    def get_run(self, run_id: str) -> ResearchRun: ...
    def list_runs(self, cursor: str | None = None) -> Page[ResearchRun]: ...
    def list_threads(self, cursor: str | None = None) -> Page[ResearchThread]: ...
    def list_sources(self, thread_id: str, cursor: str | None = None) -> Page[ResearchSource]: ...
    def list_artifacts(
        self, thread_id: str, cursor: str | None = None
    ) -> Page[ResearchArtifact]: ...
    def get_artifact(self, artifact_id: str) -> ResearchArtifact: ...
```

#### Logic / Algorithm

1. Delete `self._capabilities` from `__init__`; the constructor keeps only `_client` and `_routes`.
2. Delete `_require_read_contract`, `capabilities`, `_raise_capability_version_error`,
   `_raise_export_version_error`, `export`, and `get_export`.
3. Remove the single `self._require_read_contract()` line from each of the six read methods, leaving
   each method as one client call plus one `to_domain()`.
4. Drop the now-unused imports: `NoReturn`, `CliError`, `CliErrorCode`, `usage_error`,
   `ResearchCapabilities`, `ResearchExport`, `ResearchExportRequest`, `ApiResearchCapabilities`,
   `ApiResearchExport`, `ApiResearchExportRequest`.
5. Update the module header to drop "and capability validation" and the export sentence.

#### Edge Cases & Error Handling

- **Read hits a route that does not exist (`/research/runs`, `/sources`, `/artifacts`):** the
  `ApiProblemMapper` maps 404 to `OPERATION_FAILED` with "The requested Vidbyte resource was not
  found." That is now the terminal error rather than being rewritten to `API_PROTOCOL_ERROR`. This
  is the intended behavior change.
- **Auth failure (401/403):** unchanged; `ApiProblemMapper` still returns `AUTH_REQUIRED` and the
  gateway no longer has an intermediate handler that could reclassify it. Previously
  `_raise_capability_version_error` re-raised non-`OPERATION_FAILED` codes unchanged, so this path
  is behaviorally identical.
- **Transport failure:** unchanged; `from_transport` returns retryable `API_UNAVAILABLE`.
- **No caching regression:** the deleted `self._capabilities` cache only ever memoized the probe.
  Nothing else read it.

### 6.2 ResearchRoutes

**File(s):** `src/vidbyte_cli/features/research/infrastructure/routes.py`
**Type:** Modified

#### What it does

Constructs research API paths with opaque segments quoted. Loses the two constants and one builder
that address routes with no backend.

#### Interface / API

```python
class ResearchRoutes:
    CREATE_RUN = "/research/run"
    RUNS = "/research/runs"
    THREADS = "/research/threads"

    def append_run(self, thread_id: str) -> str: ...
    def continue_run(self, run_id: str) -> str: ...
    def run(self, run_id: str) -> str: ...
    def sources(self, thread_id: str, cursor: str | None) -> str: ...
    def artifacts(self, thread_id: str, cursor: str | None) -> str: ...
    def artifact(self, artifact_id: str) -> str: ...
    def page(self, path: str, cursor: str | None) -> str: ...
```

#### Logic / Algorithm

1. Delete the `CAPABILITIES` and `EXPORTS` class constants.
2. Delete the `export(self, export_id)` method.
3. Update the module header sentence that describes capability and export paths as assumed forward
   contracts.

#### Edge Cases & Error Handling

`_segment` and `_cursor` are untouched, so quoting behavior for opaque identifiers is unchanged.

### 6.3 Research wire DTOs

**File(s):** `src/vidbyte_cli/features/research/infrastructure/wire.py`
**Type:** Modified

#### What it does

Maps backend JSON to domain models. Loses the three DTOs that decode responses no route produces.

#### Logic / Algorithm

1. Delete `ApiResearchCapabilities`, `ApiResearchExportRequest`, and `ApiResearchExport`.
2. Drop `ExportScope`, `ResearchCapabilities`, `ResearchExport`, and `ResearchExportRequest` from
   the `..domain` import block.
3. Confirm `_TO_DOMAIN_KIND` retains a caller — `ApiResearchSource` uses it, so it stays.

#### Edge Cases & Error Handling

`ApiResearchPage` is generic over `_WireItem` and is used by four list methods; it is untouched.

### 6.4 Research domain models

**File(s):** `src/vidbyte_cli/features/research/domain/models.py`
**Type:** Modified

#### What it does

Holds the transport-independent research vocabulary. Loses the capability and export types.

#### Logic / Algorithm

1. Delete `ResearchCapabilities`, `ExportScope`, `ResearchExportRequest`, and `ResearchExport`.
2. `Page` sits between `ResearchCapabilities` and `ExportScope` in the current file; keep `Page`
   in place and remove only the classes around it.
3. Check remaining imports: `datetime` is still needed by `ResearchRun`/`ResearchThread`;
   `model_validator` is still needed by `ResearchRunRequest.reject_conflicting_domains`;
   `Generic`/`TypeVar` still needed by `Page`. No import line should become unused, but ruff
   will confirm.

#### Edge Cases & Error Handling

`ResearchExportRequest.validate_scope` carried the only per-scope validation in the domain. It is
deleted along with its model; no other model references `ExportScope`.

### 6.5 ResearchGateway protocol

**File(s):** `src/vidbyte_cli/features/research/domain/ports.py`
**Type:** Modified

#### Interface / API

```python
class ResearchGateway(Protocol):
    def start(self, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted: ...
    def add(
        self, thread_id: str, request: ResearchRunRequest, idempotency_key: str
    ) -> ResearchRunAccepted: ...
    def resume(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted: ...
    def get_run(self, run_id: str) -> ResearchRun: ...
    def list_runs(self, cursor: str | None = None) -> Page[ResearchRun]: ...
    def list_threads(self, cursor: str | None = None) -> Page[ResearchThread]: ...
    def list_sources(self, thread_id: str, cursor: str | None = None) -> Page[ResearchSource]: ...
    def list_artifacts(
        self, thread_id: str, cursor: str | None = None
    ) -> Page[ResearchArtifact]: ...
    def get_artifact(self, artifact_id: str) -> ResearchArtifact: ...
```

#### Logic / Algorithm

1. Delete the `capabilities`, `export`, and `get_export` protocol members.
2. Drop `ResearchCapabilities`, `ResearchExport`, `ResearchExportRequest` from the `.models` import.

### 6.6 Domain package exports

**File(s):** `src/vidbyte_cli/features/research/domain/__init__.py`
**Type:** Modified

Remove `ExportScope`, `ResearchCapabilities`, `ResearchExport`, `ResearchExportRequest` from both
the import block and `__all__`, keeping both lists alphabetized as they are today.

### 6.7 Research query and export services

**File(s):** `src/vidbyte_cli/features/research/application/queries.py`
**Type:** Modified

#### What it does

`ResearchQueryService` stays as the thin typed read layer. `ResearchExportService` is deleted
outright.

#### Interface / API

```python
class ResearchQueryService:
    def __init__(self, gateway: ResearchGateway) -> None: ...
    def status(self, run_id: str) -> ResearchRun: ...
    def runs(self, cursor: str | None = None) -> Page[ResearchRun]: ...
    def threads(self, cursor: str | None = None) -> Page[ResearchThread]: ...
    def sources(self, thread_id: str, cursor: str | None = None) -> Page[ResearchSource]: ...
    def artifacts(self, thread_id: str, cursor: str | None = None) -> Page[ResearchArtifact]: ...
    def artifact(self, artifact_id: str) -> ResearchArtifact: ...
```

#### Logic / Algorithm

1. Delete `ResearchQueryService.capabilities`.
2. Delete the whole `ResearchExportService` class.
3. Drop the now-unused imports: `hashlib`, `IdempotencyProvider`, `OperationRecorder`,
   `ResearchCapabilities`, `ResearchExport`, `ResearchExportRequest`.
4. Keep `CliError`/`CliErrorCode` — `_require_id` still raises `INVALID_ARGUMENT`.

#### Edge Cases & Error Handling

`application/ports.py` (`IdempotencyProvider`, `OperationRecorder`) is **not** deleted:
`ResearchService` in `service.py` still depends on both for the mutation journal.

### 6.8 Application package exports

**File(s):** `src/vidbyte_cli/features/research/application/__init__.py`
**Type:** Modified

Remove `ResearchExportService` from the `.queries` import and from `__all__`.

### 6.9 Export commands

**File(s):** `src/vidbyte_cli/features/research/commands/exports.py`
**Type:** Deleted

All four command classes target an API that does not exist. `raise_safe_validation` retains a caller
inside `commands/common.py` itself, so the helper does not become orphaned by this deletion.

### 6.10 Research query commands

**File(s):** `src/vidbyte_cli/features/research/commands/queries.py`
**Type:** Modified

Delete `ResearchCapabilitiesCommand`. Every other command class in the file is unchanged. The module
header's mention of "capability commands" is corrected.

### 6.11 Research command registrar

**File(s):** `src/vidbyte_cli/features/research/commands/registrar.py`
**Type:** Modified

#### Interface / API

```python
class ResearchCommandRegistrar:
    def register(self, parent: click.Group, environment: Mapping[str, str]) -> None: ...
    def _enabled(self, environment: Mapping[str, str]) -> bool: ...
    def _register_queries(self, research: click.Group) -> None: ...
```

#### Logic / Algorithm

1. Delete the `from .exports import (...)` block.
2. Drop `ResearchCapabilitiesCommand` from the `.queries` import.
3. Remove the `ResearchCapabilitiesCommand().register(research)` line and the
   `self._register_exports(research)` call.
4. Delete the `_register_exports` method.

The class keeps three methods, so it stays within the field guide's shallow-call-chain expectation:
`register` calls `_enabled` and `_register_queries`, neither of which delegates further.

### 6.12 Research presenter

**File(s):** `src/vidbyte_cli/features/research/presentation/presenter.py`
**Type:** Modified

Delete `ResearchPresenter.capabilities` and `ResearchPresenter.export`, and drop
`ResearchCapabilities` and `ResearchExport` from the `..domain` import. `ArtifactOutputWriter`,
`ResearchProgressObserver`, and every other renderer are untouched — in particular the artifact
`--output` path and its `usage_error` calls stay exactly as they are, since they are out of scope.

### 6.13 ApplicationContext wiring

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

#### Logic / Algorithm

1. Delete the `research_export_service()` accessor.
2. Delete the `self._research_exports: ResearchExportService | None = None` field initializer.
3. Remove `ResearchExportService` from the `TYPE_CHECKING` import block.

`research_query_service()`, `research_gateway()`, `research_watcher()`, `_idempotency_provider()`,
and `_research_operation_recorder()` are all retained — the last two still serve `ResearchService`.

#### Edge Cases & Error Handling

The accessors are lazily constructed inside a `if self._x is None` guard; deleting one cannot affect
the construction order of the others.

### 6.14 Offline smoke cases

**File(s):** `scripts/smoke.py`
**Type:** Modified

Delete these five `SmokeCase` entries, which would otherwise fail with a Click "no such command"
error once the commands are gone:

```text
SmokeCase(("research", "capabilities", "--help")),
SmokeCase(("research", "export", "artifact", "--help")),
SmokeCase(("research", "export", "thread", "--help")),
SmokeCase(("research", "export", "portfolio", "--help")),
SmokeCase(("research", "export", "status", "--help")),
```

The remaining 12 research cases stay. The `import vidbyte_cli.features.research.application` line
stays valid.

### 6.15 Folder READMEs

**File(s):** `src/vidbyte_cli/features/research/domain/README.md`,
`src/vidbyte_cli/features/research/application/README.md`,
`src/vidbyte_cli/features/research/infrastructure/README.md`
**Type:** Modified

Each names the capability/export types or services it owns. Update the affected sentences only — the
agent-oriented folder index format established in commit `991ffa1` is preserved.

---

## 7. Data Model Changes

N/A — the CLI has no database. The pydantic models removed in §6.4 are in-process request/response
vocabulary, not persisted schema. There is no on-disk record whose shape changes: the operation
journal writes `operation_id`, `command`, `idempotency_key`, `request_fingerprint`, and
`recovery_command`, none of which are export-specific fields.

---

## 8. API Changes

N/A — this is a client. No endpoint is defined, published, or modified by this repo.

For reference, the two client-side paths that stop being requested:

| Path | Change | Reason |
|------|--------|--------|
| `GET /research/capabilities` | No longer requested | Route was never implemented backend-side |
| `POST /research/exports`, `GET /research/exports/{id}` | No longer requested | No backend export API |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/research-drop-capabilities-probe.md` | This design doc |
| MODIFY | `src/vidbyte_cli/features/research/infrastructure/api_gateway.py` | Drop probe, capability cache, both version raisers, export methods |
| MODIFY | `src/vidbyte_cli/features/research/infrastructure/routes.py` | Drop `CAPABILITIES`, `EXPORTS`, `export()` |
| MODIFY | `src/vidbyte_cli/features/research/infrastructure/wire.py` | Drop three DTOs with no route |
| MODIFY | `src/vidbyte_cli/features/research/infrastructure/README.md` | Stale ownership description |
| MODIFY | `src/vidbyte_cli/features/research/domain/models.py` | Drop capability and export vocabulary |
| MODIFY | `src/vidbyte_cli/features/research/domain/ports.py` | Drop three protocol members |
| MODIFY | `src/vidbyte_cli/features/research/domain/__init__.py` | Drop four re-exports |
| MODIFY | `src/vidbyte_cli/features/research/domain/README.md` | Stale ownership description |
| MODIFY | `src/vidbyte_cli/features/research/application/queries.py` | Drop `capabilities`; delete `ResearchExportService` |
| MODIFY | `src/vidbyte_cli/features/research/application/__init__.py` | Drop one re-export |
| MODIFY | `src/vidbyte_cli/features/research/application/README.md` | Stale ownership description |
| DELETE | `src/vidbyte_cli/features/research/commands/exports.py` | Commands for a nonexistent API |
| MODIFY | `src/vidbyte_cli/features/research/commands/queries.py` | Delete `ResearchCapabilitiesCommand` |
| MODIFY | `src/vidbyte_cli/features/research/commands/registrar.py` | Drop export group and capabilities registration |
| MODIFY | `src/vidbyte_cli/features/research/presentation/presenter.py` | Drop two renderers |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Drop `research_export_service()` and its field |
| MODIFY | `scripts/smoke.py` | Drop five smoke cases for removed commands |

**Totals:** 1 created, 16 modified, 1 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte public API | `POST /api/v1/research/run`, `/threads/{id}/run`, `/runs/{id}/continue` | Confirmed mutation routes | None from this change |
| Vidbyte public API | `GET /api/v1/research/runs/{run_id}` | Confirmed read route backing `status`/`watch` | None from this change |
| Vidbyte public API | `GET /research/capabilities` | **Removed as a dependency** | Eliminated |
| Vidbyte public API | `/research/exports` | **Removed as a dependency** | Eliminated |
| `httpx` | as pinned in `pyproject.toml` | Transport | Unchanged |
| `pydantic` | as pinned in `pyproject.toml` | DTO decoding | Unchanged; three models removed |
| `click` | as pinned in `pyproject.toml` | Command tree | Unchanged; five commands removed |

No dependency is added, removed, or version-changed in `pyproject.toml`.

---

## 11. Rollout & Deployment

- **Feature flags:** the existing `VIDBYTE_EXPERIMENTAL_RESEARCH` env gate in
  `ResearchCommandRegistrar._enabled` is untouched. Setting it to `0`/`false`/`no`/`off` still
  removes the whole research group.
- **Breaking change:** yes in principle — `research capabilities` and the four `research export`
  subcommands disappear. In practice no user can be depending on them: every one of them fails
  today with either the version error or a 404, on every invocation, against every deployed backend.
  There is no working behavior to preserve.
- **Deployment order:** none. Single repo, client-only, no coordinated backend change.
- **Rollback:** revert the PR. The change is pure deletion with no migration and no persisted state,
  so a revert fully restores the prior behavior.
- **Reaching `main`:** this PR targets `feat/research-api-wiring` and does not reach `main`. `main`
  has no research feature and cannot accept these commits (§3). A separate `-target-main` port is
  required and is tracked in §12.

---

## 12. Open Questions

- [ ] The `-target-main` port of the research feature is unscheduled. It must reconcile against
      `main`'s slimmer platform (`ApiClient` without `shape=`/`idempotency_key`/`request()`, and
      five missing `lib/` modules). Until it happens, no research command ships.
- [ ] `ResearchRoutes` omits the `/api/v1` prefix that `research_public.py` and `research_read.py`
      both declare via `APIRouter(prefix="/api/v1/research", ...)`. Deliberately out of scope here;
      `status`/`watch`/`resume` will still 404 until it is fixed. Should be the next PR on this
      branch.
- [ ] `research runs list`, `threads list`, `sources list`, and `artifacts list` have no backend
      route at all — only `GET /portfolio` and `GET /threads/{id}` exist. Decide whether to remap
      them onto the real routes or remove them, in the same spirit as this PR.
- [ ] `docs/design/python-cli-research-harness-program.md` (1650 lines, 67 capability/export
      mentions) is now partly stale. Left untouched per the field guide's "touch only the files the
      design doc assigns" rule. Needs its own docs pass.

---

## 13. Alternatives Considered

### Alternative 1: Make the probe fail-soft

- **What:** catch the 404 in `capabilities()` and return an empty `ResearchCapabilities()` instead
  of raising, leaving `_require_read_contract()` in place.
- **Why rejected:** it keeps one extra HTTP round trip per read — and per poll tick, so ~300 wasted
  requests on a 10-minute watch — to obtain a value that, once export is gone, nothing reads. It
  also preserves a "version probe" concept whose premise (an old server exists) is false, which
  misleads the next reader into thinking version negotiation is a live concern.

### Alternative 2: Implement `/research/capabilities` in the backend

- **What:** add the route to `research_read.py` so the probe succeeds.
- **Why rejected:** it builds a backend feature whose only consumer is a client check that exists to
  guard a second feature that also does not exist. That is two dead things propping each other up.
  If capability negotiation is ever genuinely needed, it should be designed against a real
  requirement, not retrofitted to satisfy an existing probe.

### Alternative 3: Keep the export commands and only delete the probe

- **What:** remove `_require_read_contract` but leave `research export *` registered, dropping just
  the `provider not in capabilities.export_providers` check.
- **Why rejected:** the export commands would then POST to `/research/exports` and 404. Keeping four
  user-visible commands that cannot succeed is worse than removing them — it advertises capability
  the product does not have, and the finding's own framing is that export checks should go away
  *with* the export commands rather than be patched.

### Alternative 4: Target `main` with this PR

- **What:** open against `main` so the fix reaches the shipped CLI.
- **Why rejected:** `main` has no `features/research`, and the platform modules the feature imports
  were never landed there. The PR diff would be 121 files, +7013/−3249, and would amount to porting
  the entire research feature across a deliberate platform rewrite — a much larger change than the
  one requested. Chosen explicitly by the user; the port is tracked as a follow-up in §12.

---

## 14. Verification

Canonical gate, per the field guide's "Verify with the canonical gate" rule:

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

This covers ruff lint, ruff format `--check`, mypy strict over `src`, `compileall`, the offline
`scripts/smoke.py` command-tree render, an isolated sdist/wheel build, `twine check`, and a
clean-venv wheel install with console smoke.

Change-specific acceptance checks:

```bash
# No capability or export symbol survives in the feature
grep -rn -i "capabilit" src/vidbyte_cli/features/          # expect: no matches
grep -rn -i "export" src/vidbyte_cli/features/ | grep -v "__all__"   # expect: no matches

# No route constant for a nonexistent endpoint
grep -rn "CAPABILITIES\|EXPORTS" src/                      # expect: no matches

# The poll interval stayed a local constant
grep -n "interval_seconds" src/vidbyte_cli/lib/polling/poller.py

# Command tree no longer advertises the removed commands
python -m vidbyte_cli research --help                      # expect: no 'capabilities', no 'export'
```
