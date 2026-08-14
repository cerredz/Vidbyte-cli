# Design Doc: Research Against the Production API Surface

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-14
**Last Updated:** 2026-08-14

---

## 1. Overview

This change gives the CLI a working `research` command group that speaks the six research
routes actually running in production, and it implements the HTTP transport those commands
need — `lib/api/client.py` is still a stub on `main`, so today no CLI command can make a
network request at all. The abandoned side branch `feat/research-api-wiring` was written
against a hoped-for API with twelve routes; roughly half of what it built (sources,
artifacts, capabilities, exports, run listing) has no backend behind it and every read on
that branch failed a capability probe against a route that does not exist. This PR ports
forward only the transport the CLI is missing, rewrites it into `main`'s current
conventions, and implements `research start`, `add`, `resume`, `status`, `watch`, `threads`,
and `thread` against the real contract — including the identifier rule that makes them
usable: the only thread id the CLI ever shows or accepts is the server's public share
token.

---

## 2. Goals & Non-Goals

### Goals

- Implement `ApiClient` for real: typed requests, explicit timeouts, bounded safe retries,
  response validation, and status-driven error classification.
- Ship a `research` command group covering the entire public API-key research surface:
  start a thread, append to a thread, continue a terminal run, read one run's status, watch
  one run to completion, list the caller's threads, and read one thread.
- Make every identifier the CLI prints one the user can paste back into the next command.
- Map every backend failure status onto a typed `CliError` subclass whose prose names what
  the caller should do next, with no backend response text quoted.
- Poll at a rate the production weighted rate limiter can absorb.
- Keep `python scripts/run_ci.py` green, and extend `scripts/smoke.py` with the new
  credential-free contract cases.

### Non-Goals

- **Sources, artifacts, capabilities, and exports.** No backend route serves any of them.
  They are not stubbed, not hidden behind a flag, and not represented in any model.
- **Listing runs.** There is no `GET /research/runs` collection route; runs are reached
  through the ids `start`/`add`/`resume` return, or through a thread's `latest_run_id`.
- **`source_sites` and `reference_artifact_ids` request fields.** Both exist on the server
  request DTO, but choosing values requires a source-site catalogue and an artifact list the
  API-key surface does not expose. Omitted rather than exposed as unusable flags.
- **A local operation journal.** See §13, Alternative 3.
- **Deep dives, artifact deletion, favorites.** Browser-session routes, not API-key routes.
- **New test files.** The `design-doc-no-tests` workflow is in force. The existing gate —
  ruff, mypy strict, compileall, offline smoke, and the packaged-wheel verification in
  `scripts/run_ci.py` — is not weakened and must stay green.

---

## 3. Background & Context

### Why now

The seven-PR program in `docs/design/python-cli-research-harness-program.md` planned PRs
4–7 as HTTP plumbing, research domain, research commands, and API wiring. Those were built
on the side branch `feat/research-api-wiring` and never merged. Meanwhile PRs #11–#14
landed on `main` and rewrote the errors, config, auth, and runtime layers that branch was
written against. The branch is now ~6,400 lines diverged and cannot be merged; its useful
content has to be reimplemented on `main`'s conventions.

Independently, the research backend shipped. `backend/lib/app/route_rules.py:60-69` in the
`vidbyte` repository is now the authoritative list of what an API key may call, and it is
much smaller than the program document's §8 assumed.

### Current state on `main`

- `src/vidbyte_cli/lib/api/client.py:42-52` — `get`, `get_list`, and `post` all raise
  `NotImplementedFeature`. The constructor, `auth_headers()`, and the `x-api-key` header
  name (`API_KEY_HEADER_NAME`) are real and were settled by PR #14.
- `src/vidbyte_cli/lib/api/endpoints/{auth,harness}.py` — typed endpoint groups exist and
  call the stub methods.
- `lib/errors/failures.py` — 29 `CliError` subclasses. The field guide forbids constructing
  a bare `CliError(...)` or writing a module-level error constructor function.
- `lib/config/paths.py:56` — `operations_dir()` already exists, unused.
- There is no `research` anything on `main`.

### The identifier problem this design exists to solve

A research thread has two identifiers and the API deliberately publishes only one:

- `encrypted_id` is a UUIDv4 share token. `backend/lib/config/database.py:12` pins it to
  `^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$`,
  and both `POST /threads/{encrypted_id}/run` and `GET /threads/{encrypted_id}` match their
  path segment against that pattern **in transport**, before any lookup.
- `thread_id` is the internal identifier. Pasting it into a path does not 404 — it fails
  the path regex and returns 422.

The three response DTOs carry different halves of that pair:

| DTO (`backend/lib/dtos/research.py`) | `encrypted_id` | `thread_id` |
|---|---|---|
| `ResearchRunAcceptedDto` (:1380) | yes | no |
| `ResearchThreadSummaryDto` (:1407) | yes | yes |
| `ResearchRunStatusDto` (:1390) | **no** | yes |

So a naive `status` implementation prints the one identifier that cannot be used for
anything, the user pastes it into `research add`, and the server rejects it with a
transport-level validation error that explains nothing.

### Constraints discovered in the backend

- All three mutation routes require an `Idempotency-Key` header with no default
  (`backend/routes/research_public.py:34-37`); omitting it is a 422 before the orchestrator
  runs.
- All three mutation routes are `RouteBilling.PRICED`. A duplicate call costs real money.
- Research routes return their DTO **directly**. They do not use the `{success, data}`
  envelope that `backend/routes/api_contract.py` defines for other public resources.
- Failures render `backend/lib/errors/domain.py:150`:
  `{"error", "title", "subtitle", "description", "code", "incident_id"}`.
- Continuation is legal only when the run is already `PARTIAL`, `FAILED`, or
  `CREDIT_EXHAUSTED` (`backend/orchestrators/routes/research.py:372`); anything else is a
  409 with reason `not_terminal_resumable`.
- Rate limiting is **weighted**, not per-request. `backend/lib/configs/api_config.py:121-123`
  weights `POST /api/v1/research/run` at 14 and `.../continue` at 8; unlisted GETs take the
  default weight. API-key callers land on spend tiers starting at 30 weighted requests per
  minute. One `research start` therefore consumes nearly half of an entry-tier minute, and
  a two-second poll loop would consume the entire remainder.
- The request DTO is `extra="forbid"` with `resource_kinds` at `min_length=1`, so unset
  options must be **omitted** from the JSON body, never sent as `null` or `[]`.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli research start <PROMPT>` submits `POST /api/v1/research/run` and prints the
   new thread id, the run id, and the admitted status.
2. `vidbyte-cli research add <THREAD_ID> <PROMPT>` submits
   `POST /api/v1/research/threads/{encrypted_id}/run` and prints the same three fields.
3. `vidbyte-cli research resume <RUN_ID>` submits
   `POST /api/v1/research/runs/{run_id}/continue` with no request body.
4. `vidbyte-cli research status <RUN_ID>` reads `GET /api/v1/research/runs/{run_id}` and
   prints run id, status, phase, continuation count, and last-updated time.
5. `vidbyte-cli research watch <RUN_ID>` polls the same route until the run reaches a
   terminal status, emitting one transition record per observed change.
6. `vidbyte-cli research threads` reads `GET /api/v1/research/portfolio` and prints one
   bounded page of threads plus the forward cursor, if any.
7. `vidbyte-cli research thread <THREAD_ID>` reads
   `GET /api/v1/research/threads/{encrypted_id}` and prints one thread with its rollups.
8. Every thread identifier the CLI prints is the server's `encrypted_id`. The server's
   internal `thread_id` is never printed, stored, or accepted as input.
9. A `THREAD_ID` argument that cannot be a share token is rejected locally with exit status
   2 before any credential is resolved or any request is sent.
10. Each of the three mutation commands sends an `Idempotency-Key`, accepts an explicit one
    via `--idempotency-key`, and reports the key it used in the machine-readable document.
11. A 409 from `resume` renders as a failure that states the resume rule — a run may be
    continued only after it settles partial, failed, or credit-exhausted.
12. A 403 renders as a failure naming the missing API-key scope (`research:read` or
    `research:write`), distinct from the 401 "not logged in" failure.
13. Registration of the whole `research` group is synchronous and free of credential,
    filesystem, and network access, so every `--help` path stays offline.

### Non-Functional Requirements

- **Rate:** `watch` starts at a 10-second interval and backs off multiplicatively to a
  60-second ceiling. It never polls faster than once per 10 seconds.
- **Retries:** at most 3 attempts. `GET`/`HEAD`/`OPTIONS` are always retry-eligible; `POST`
  is eligible only while carrying an idempotency key. Backoff is exponential with jitter,
  capped at 10 seconds, and honours `Retry-After` up to that cap.
- **Security:** no failure prose may quote a credential, a prompt, a URL, or a backend
  response body. `CliError.cause` remains private and unserialized. The API key travels only
  in the `x-api-key` header set by `ApiClient.auth_headers()`.
- **Bounded input:** responses are rejected above 5 MB, on a non-JSON content type, and on
  an empty body, before parsing.
- **Observability:** every failure carries `code`, `description`, `trace`, `file_path`, and
  — when the response supplied one — a `request_id` taken from the `x-request-id` **header**.
- **Reliability:** a `watch` timeout leaves the remote run untouched and tells the caller
  the `research status` command that recovers it.

---

## 5. High-Level Design

The change has two halves that stack cleanly.

**The transport half** fills in `lib/api/`. `ApiClient` keeps the constructor and header
policy PR #14 settled and gains a real `_send` loop: build an absolute URL from a validated
relative path, serialize the body once, attach headers once, and re-issue that identical
request while `RetryPolicy` says to. Three new modules split the concerns the loop needs —
`retry.py` decides retry eligibility and delay, `problem.py` turns a non-2xx status into a
typed failure, and `response.py` validates a success body into a Pydantic model. The only
new concept crossing the boundary is `ResponseShape`, which lets an endpoint group state
whether its route returns a bare DTO (research) or the `{success, data}` envelope (the
pre-existing auth and harness groups).

**The research half** follows the shape `main` already uses for a feature: wire models in
`types/research.py` next to `types/harness.py`, a typed endpoint group in
`lib/api/endpoints/research.py` next to `endpoints/harness.py`, and one Click adapter file
per verb in `commands/research/` next to `commands/harness/`. There is no separate domain,
application, infrastructure, and presentation hierarchy — the side branch's five-layer
structure existed to insulate an unknown API, and the API is now known.

The identifier rule is enforced in exactly one place, in the models. `ResearchRunAccepted`
and `ResearchThreadSummary` bind their `thread_id` field to the wire key `encrypted_id`
through a Pydantic alias with `populate_by_name` left off, so the server's internal
`thread_id` key cannot populate it. `ResearchRunStatus` declares no thread field at all.
All three models are `extra="ignore"`, so the internal identifier arrives, is dropped, and
never reaches a renderer.

```
research start "..."
  |
  v
ResearchStartCommand.execute
  |  ThreadId/IdempotencyKey validation (local, pre-credential)
  v
ApplicationContext.research_endpoints()
  |  -> CredentialResolver -> ApiClient(config, credentials)
  v
ResearchEndpoints.create_run(request, key)
  |
  v
ApiClient.post(path, body, ResearchRunAccepted, shape=DIRECT, idempotency_key=key)
  |     _url -> _headers -> _send loop -> RetryPolicy.decide
  |                                    -> ApiProblemMapper (non-2xx)
  |                                    -> ResponseDecoder  (2xx)
  v
ResearchRenderer.accepted(...) -> (OutputDocument, human text)
  |
  v
OutputManager.result(...)
```

`watch` reuses that path in a loop owned by `ResearchWatchCommand`: fetch, fingerprint,
emit a transition only when the fingerprint changes, stop on a terminal status, otherwise
sleep and back off.

---

## 6. Detailed Design

### 6.1 `ResponseShape` and `ResponseDecoder`

**File(s):** `src/vidbyte_cli/lib/api/response.py`
**Type:** New file

#### What it does

Validates one HTTP success response into a typed model, having first bounded and
type-checked the body. Endpoint groups declare which of three wire shapes their route uses,
so the envelope rule is stated per route rather than assumed globally.

#### Interface / API

```python
class ResponseShape(StrEnum):
    DIRECT = "direct"
    ENVELOPE = "envelope"
    LIST_ENVELOPE = "list_envelope"


class ResponseDecoder:
    def one(self, response: httpx.Response, model: type[TModel], shape: ResponseShape) -> TModel: ...
    def many(self, response: httpx.Response, model: type[TModel]) -> list[TModel]: ...
```

#### Logic / Algorithm

1. `_payload` rejects a 204, a content type that is neither `application/json` nor a
   `+json` suffix type, a declared `Content-Length` above 5 MB, an empty body, and an actual
   body above 5 MB — each as `ApiResponseUnsupported`.
2. It then parses the bytes as JSON, mapping a decode failure to the same error.
3. `one` unwraps the envelope when the shape is `ENVELOPE`, then validates into `model`.
4. `_unwrap` requires a JSON object, refuses `success: false`, and requires a non-null
   `data` key.
5. `many` always unwraps, then validates a list of `model`.

#### Edge Cases & Error Handling

- Every rejection is `ApiResponseUnsupported`, so a caller cannot tell a wrong content type
  from a schema drift — deliberate, because both mean "this CLI cannot read this backend"
  and the distinction would only be useful if the prose quoted the body, which is banned.
- A `DIRECT` route returning an envelope fails validation rather than silently unwrapping.
- The size bound is checked on the declared header *and* the materialized body, because a
  chunked response declares no length.

---

### 6.2 `RetryPolicy`

**File(s):** `src/vidbyte_cli/lib/api/retry.py`
**Type:** New file

#### What it does

Answers one question — should this attempt be repeated, and after how long — for a single
transport outcome, without performing the sleep itself.

#### Interface / API

```python
@dataclass(frozen=True)
class RequestMetadata:
    method: str
    has_idempotency_key: bool = False


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_seconds: float = 0.0
    delay_clamped: bool = False


class RetryPolicy:
    def decide(self, request: RequestMetadata, attempt: int, response: httpx.Response | None, error: Exception | None) -> RetryDecision: ...
```

#### Logic / Algorithm

1. Refuse immediately at `attempt >= _MAX_ATTEMPTS` (3) or when the method is not
   retry-safe. Safe means `GET`/`HEAD`/`OPTIONS`, or `POST` while an idempotency key is
   attached.
2. Treat `ConnectError`, `ConnectTimeout`, `ReadTimeout`, and `RemoteProtocolError` as
   retryable transport failures; treat 408, 429, 502, 503, and 504 as retryable statuses.
3. Prefer a `Retry-After` header, parsed as either seconds or an HTTP date, clamped to
   `_MAXIMUM_DELAY_SECONDS` (10) with `delay_clamped` set when the clamp bites.
4. Otherwise use `0.25 * 2**(attempt-1)`, capped at 4 seconds, plus up to 0.25 seconds of
   jitter, then clamped to the same ceiling.

#### Edge Cases & Error Handling

- A `POST` without an idempotency key is never retried, so a priced mutation cannot be
  charged twice by this layer.
- A malformed `Retry-After` is ignored rather than treated as zero.
- A `Retry-After` date in the past yields 0, not a negative sleep.

---

### 6.3 `ApiProblemMapper`

**File(s):** `src/vidbyte_cli/lib/api/problem.py`
**Type:** New file

#### What it does

Turns a non-2xx response, or a transport exception, into the right `CliError` subclass. It
reads the status code and the `x-request-id` header, and nothing else — never the response
body.

#### Interface / API

```python
class ApiProblemMapper:
    def from_response(self, response: httpx.Response) -> CliError: ...
    def from_transport(self, error: httpx.HTTPError) -> CliError: ...
```

#### Logic / Algorithm

1. Extract a bounded `x-request-id` header, or `None`.
2. `match` on the status code, one arm per class of failure:

| Status | Failure class | Exit |
|---|---|---|
| 401 | `ApiCredentialsRejected` | 4 |
| 403 | `ApiPermissionDenied` | 4 |
| 402 | `ApiCreditExhausted` | 5 |
| 404 | `ApiResourceNotFound` | 1 |
| 409 | `ApiRequestConflicted` | 2 |
| 400, 422 | `ApiRequestRejected` | 2 |
| 429 | `ApiRateLimited` | 1 |
| >= 500 | `ApiUnavailable` | 1 |
| anything else | `ApiOperationFailed` | 1 |

3. `from_transport` always returns `ApiUnreachable`, carrying the httpx error privately as
   `cause`.

#### Edge Cases & Error Handling

- 403 is separated from 401 because the remedies differ completely: 401 means log in, 403
  means the key authenticated but lacks `research:read` or `research:write`. Collapsing
  them sends every scope problem to a login prompt that will not fix it.
- 409 is separated from 400/422 because on this surface it has exactly one meaning worth
  naming: a run may be continued only from `partial`, `failed`, or `credit_exhausted`.
- 429 is separated from 5xx because the remedy is "poll less often", not "retry later".

---

### 6.4 `ApiClient`

**File(s):** `src/vidbyte_cli/lib/api/client.py`
**Type:** Modified

#### What it does

Executes one typed request against the invocation's resolved host and credential, retrying
where the policy allows, and returning a validated model. Retains the constructor,
`auth_headers()`, and `API_KEY_HEADER_NAME` exactly as PR #14 left them.

#### Interface / API

```python
class ApiClient:
    def __init__(self, config: ResolvedConfig, credentials: Credentials) -> None: ...
    def auth_headers(self) -> dict[str, str]: ...
    def get(self, path: str, model: type[TModel], *, shape: ResponseShape = ResponseShape.ENVELOPE) -> TModel: ...
    def get_list(self, path: str, model: type[TModel]) -> list[TModel]: ...
    def post(self, path: str, body: BaseModel, model: type[TModel], *, shape: ResponseShape = ResponseShape.ENVELOPE, idempotency_key: str | None = None) -> TModel: ...
    def request(self, method: str, path: str, *, response_model: type[TModel], response_shape: ResponseShape, body: BaseModel | None = None, idempotency_key: str | None = None) -> TModel: ...
    def close(self) -> None: ...
```

#### Logic / Algorithm

1. `_url` rejects any path that is not a single-slash-prefixed relative path, and any path
   carrying a scheme or netloc, as `ApiRouteMisconfigured` — a CLI defect, exit 70.
2. `_headers` sets `Accept`, `Content-Type` when a body exists, `User-Agent` from
   `current_version()`, the `x-api-key` credential from `auth_headers()`, and
   `Idempotency-Key` when one is supplied.
3. `_body` serializes with `model_dump_json(exclude_none=True)` **once**, so every attempt
   sends byte-identical content under the same idempotency key.
4. `_send` loops: issue the request, catch `httpx.HTTPError`, ask `RetryPolicy.decide`,
   sleep and continue while it says retry, then raise through `ApiProblemMapper` or return
   the response.
5. `request` hands the successful response to `ResponseDecoder.one`.
6. The underlying `httpx.Client` is created lazily on first send, so constructing an
   `ApiClient` — which `HarnessContext.harness_endpoints()` does eagerly — opens nothing.

#### Edge Cases & Error Handling

- `exclude_none=True` is what keeps unset request options out of the JSON body, which the
  server's `extra="forbid"` DTO with `min_length=1` list fields requires.
- The default `shape` stays `ENVELOPE` so the pre-existing `AuthEndpoints` and
  `HarnessEndpoints` call sites keep their meaning unchanged.
- A clamped `Retry-After` is not surfaced to the user; it is a server-pacing detail the
  caller cannot act on.

---

### 6.5 Research wire models

**File(s):** `src/vidbyte_cli/types/research.py`
**Type:** New file

#### What it does

Declares every request and response shape on the research surface, the two value classes
that guard the identifiers, and the status vocabulary the commands branch on.

#### Interface / API

```python
class ResearchStatus(StrEnum):
    ADMITTING = "admitting"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CREDIT_EXHAUSTED = "credit_exhausted"

    def is_terminal(self) -> bool: ...


class ResearchSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ResearchKind(StrEnum):
    PAPER = "paper"
    WEB = "web"


class ThreadId:
    def __init__(self, value: str) -> None: ...
    @classmethod
    def parse(cls, value: str) -> ThreadId: ...
    @classmethod
    def normalize(cls, value: str) -> str: ...
    def __str__(self) -> str: ...


class IdempotencyKey:
    def __init__(self, value: str) -> None: ...
    @classmethod
    def create(cls, explicit: str | None) -> IdempotencyKey: ...
    def __str__(self) -> str: ...


class ResearchRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prompt: str = Field(min_length=1, max_length=20_000)
    request_schema_version: Literal[2] = 2
    size: ResearchSize | None = None
    target_sources: int | None = Field(default=None, ge=1, le=1_000)
    search_calls: int | None = Field(default=None, ge=1, le=100)
    resource_kinds: list[ResearchKind] | None = Field(default=None, min_length=1, max_length=2)
    include_domains: list[str] | None = Field(default=None, max_length=50)
    exclude_domains: list[str] | None = Field(default=None, max_length=50)
    published_after: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    language: str | None = Field(default=None, min_length=2, max_length=12)
    max_run_cost_cents: int | None = Field(default=None, ge=1, le=100_000)


class ResearchRunAccepted(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    thread_id: str = Field(alias="encrypted_id")
    run_id: str
    status: ResearchStatus


class ResearchRunStatus(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    run_id: str
    status: ResearchStatus
    phase: str
    continuation_count: int = Field(ge=0)
    updated_at: datetime


class ResearchThreadSummary(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    thread_id: str = Field(alias="encrypted_id")
    title: str
    run_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    latest_run_id: str | None = None
    latest_run_status: ResearchStatus | None = None
    created_at: datetime
    updated_at: datetime


class ResearchThreadDetail(ResearchThreadSummary):
    latest_run_phase: str | None = None
    favorite: bool = False


class ResearchPortfolioPage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    threads: list[ResearchThreadSummary]
    next_cursor: str | None = None
```

#### Logic / Algorithm

1. `ThreadId.parse` matches the UUIDv4 share-token pattern and raises
   `ResearchThreadIdInvalid` on a miss. `normalize` is the Pydantic entry point bound as
   `Annotated[str, AfterValidator(ThreadId.normalize)]` for the append path parameter.
2. `IdempotencyKey.create` returns a fresh `uuid4()` when no explicit key is given, and
   otherwise validates 8–128 URL-safe characters, raising `ResearchIdempotencyKeyInvalid`.
3. `ResearchRunCreateRequest.normalize_domains` lowercases, strips a trailing dot, and
   rejects any value containing `/` or `:`, matching the server's hostname-only rule.
4. `validate_domain_filters` rejects an include/exclude overlap, which the server also
   rejects — catching it locally avoids spending a request to learn it.
5. `ResearchStatus.is_terminal` returns true for `completed`, `partial`, `failed`,
   `cancelled`, and `credit_exhausted`.

#### Edge Cases & Error Handling

- `populate_by_name` is deliberately **not** enabled on the aliased models. With it off, only
  the wire key `encrypted_id` can populate `thread_id`, so the server's internal `thread_id`
  key falls through to `extra="ignore"` and is discarded. Enabling it would make the two keys
  interchangeable and reintroduce exactly the bug this design exists to prevent.
- `ResearchRunStatus` declares no thread field, so `status` and `watch` structurally cannot
  print an unusable identifier.
- `extra="ignore"` on every response model means a future backend field is additive, not
  breaking.
- `request_schema_version` is pinned to `Literal[2]`; the server accepts 1 or 2 and defaults
  to 2, and only 2 supports the reference-artifact field a later release may add.

---

### 6.6 `ResearchEndpoints`

**File(s):** `src/vidbyte_cli/lib/api/endpoints/research.py`
**Type:** New file

#### What it does

Typed wrappers for the six `/api/v1/research/*` routes, matching the existing
`HarnessEndpoints` and `AuthEndpoints` pattern. Every route declares `ResponseShape.DIRECT`.

#### Interface / API

```python
class ResearchEndpoints:
    def __init__(self, client: ApiClient) -> None: ...
    def create_run(self, request: ResearchRunCreateRequest, idempotency_key: str) -> ResearchRunAccepted: ...
    def append_run(self, thread_id: str, request: ResearchRunCreateRequest, idempotency_key: str) -> ResearchRunAccepted: ...
    def continue_run(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted: ...
    def get_run(self, run_id: str) -> ResearchRunStatus: ...
    def get_portfolio(self, cursor: str | None, limit: int | None) -> ResearchPortfolioPage: ...
    def get_thread(self, thread_id: str) -> ResearchThreadDetail: ...
```

#### Logic / Algorithm

1. Path constants live at module scope; opaque segments are percent-encoded with
   `quote(value, safe="")` so an identifier can never alter route structure.
2. `continue_run` calls `ApiClient.request` with `body=None`, because the route accepts no
   request body.
3. `get_portfolio` appends `cursor` and `limit` through `urlencode` only when set, so the
   server owns both defaults.

#### Edge Cases & Error Handling

- `thread_id` is already validated by the command layer; the encoding here is
  defence in depth, not the guard.
- A `limit` outside 1–100 is rejected by Click's `IntRange` before reaching this layer.

---

### 6.7 Research command group

**File(s):** `src/vidbyte_cli/commands/research/__init__.py`,
`start.py`, `add.py`, `resume.py`, `status.py`, `watch.py`, `threads.py`, `thread.py`,
`options.py`, `render.py`
**Type:** New files

#### What it does

One Click adapter class per verb, matching `commands/harness/`. Shared run-request options
live in `options.py`; all human and machine rendering lives in `render.py`.

#### Interface / API

```python
class ResearchRunOptions:
    """The request-shaping options `start` and `add` both accept."""
    def apply(self, command: Callable[..., None]) -> Callable[..., None]: ...
    def build(self, prompt: str, values: Mapping[str, object]) -> ResearchRunCreateRequest: ...


@dataclass(frozen=True)
class RenderedResult:
    document: OutputDocument
    human: str


class ResearchRenderer:
    def accepted(self, accepted: ResearchRunAccepted, idempotency_key: str) -> RenderedResult: ...
    def run_status(self, run: ResearchRunStatus) -> RenderedResult: ...
    def thread(self, thread: ResearchThreadDetail) -> RenderedResult: ...
    def thread_page(self, page: ResearchPortfolioPage) -> RenderedResult: ...


class ResearchWatchCommand:
    def execute(self, context: ApplicationContext, run_id: str, timeout: float | None) -> None: ...
```

#### Logic / Algorithm

`ResearchStartCommand.execute`:

1. Build the typed request from the parsed options, and the idempotency key, **before**
   resolving credentials — a malformed invocation must not require a login.
2. Call `context.research_endpoints().create_run(request, key)`.
3. Render and emit through `context.output().result(...)`.

`ResearchAddCommand.execute` is the same with `ThreadId.parse(thread_id)` as step 0.

`ResearchWatchCommand.execute`:

1. `_poll_until_terminal` fetches, computes `_fingerprint`, emits a transition through
   `OutputManager.transition` when the fingerprint changed, and returns on a terminal
   status.
2. `_fingerprint` is `f"{status}:{phase}:{updated_at}"` — the whole of what the thin status
   payload exposes.
3. `_next_delay` multiplies the current delay by `_BACKOFF_FACTOR` (1.5), capped at
   `_MAXIMUM_DELAY_SECONDS` (60.0), starting from `_INITIAL_DELAY_SECONDS` (10.0).
4. On expiry of `--timeout`, raise `ResearchWatchTimedOut`, whose hint names the exact
   `research status <run_id>` command that recovers the wait.
5. The final terminal snapshot is emitted as the command's single result document.

#### Edge Cases & Error Handling

- `admitting` and `accepted` are non-terminal, not failures; a `status` read immediately
  after `start` legitimately returns one of them.
- Ctrl-C during a `watch` sleep raises `KeyboardInterrupt`, which
  `ErrorHandler.handle` already maps to `OperationInterrupted` (exit 130) — whose
  description already states that submitted work is not cancelled by the signal. No
  signal-handling machinery is added.
- `research threads` on an account with no threads renders an explicit "No research
  threads." line rather than empty output.
- A `next_cursor` of `None` is the end of the collection; the command never loops.
- A `--timeout` shorter than one poll interval still performs one fetch before expiring.

---

### 6.8 New failure classes

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Adds one `CliError` subclass per new failure, following the field guide: `code`,
`exit_status`, and `retryable` fixed on the class; `message`, `description`, `trace`, and
`hint` authored as static text; `file_path` derived, never written.

| Class | Code | Exit | Retryable |
|---|---|---|---|
| `ApiRouteMisconfigured` | `INTERNAL_ERROR` | 70 | no |
| `ApiResponseUnsupported` | `API_PROTOCOL_ERROR` | 1 | no |
| `ApiUnreachable` | `API_UNAVAILABLE` | 1 | yes |
| `ApiCredentialsRejected` | `AUTH_REQUIRED` | 4 | no |
| `ApiPermissionDenied` | `AUTH_REQUIRED` | 4 | no |
| `ApiCreditExhausted` | `CREDIT_EXHAUSTED` | 5 | no |
| `ApiResourceNotFound` | `OPERATION_FAILED` | 1 | no |
| `ApiRequestRejected` | `INVALID_ARGUMENT` | 2 | no |
| `ApiRequestConflicted` | `INVALID_ARGUMENT` | 2 | no |
| `ApiRateLimited` | `API_UNAVAILABLE` | 1 | yes |
| `ApiUnavailable` | `API_UNAVAILABLE` | 1 | yes |
| `ApiOperationFailed` | `OPERATION_FAILED` | 1 | no |
| `ResearchThreadIdInvalid` | `INVALID_ARGUMENT` | 2 | no |
| `ResearchIdempotencyKeyInvalid` | `INVALID_ARGUMENT` | 2 | no |
| `ResearchWatchTimedOut` | `OPERATION_FAILED` | 1 | yes |

#### Edge Cases & Error Handling

- `ApiRequestConflicted`'s description states the resume rule verbatim, because that is the
  only 409 this surface produces and a generic "the request conflicted" would leave the
  caller nowhere.
- `ApiPermissionDenied`'s description names both research scopes so a caller can check the
  right one on their key without a second round trip.
- No class quotes a response body, a URL, a prompt, or a credential.

---

### 6.9 `ApplicationContext` wiring

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

#### What it does

Adds lazy construction of the API client and the research endpoint group, and a `close()`
that releases the HTTP connection pool at the end of an invocation.

#### Interface / API

```python
class ApplicationContext:
    def require_credentials(self) -> Credentials: ...
    def api_client(self) -> ApiClient: ...
    def research_endpoints(self) -> ResearchEndpoints: ...
    def close(self) -> None: ...
```

#### Logic / Algorithm

1. `require_credentials` resolves through `CredentialResolver` for the invocation's profile
   and host, raising `AuthenticationRequired` when nothing is stored — the same guard
   `HarnessContext.require_credentials` already applies.
2. `api_client` builds one `ApiClient` per invocation and caches it, so a `watch` loop
   reuses one connection pool.
3. `close` closes the client only if one was ever built; `--help` therefore closes nothing.

#### Edge Cases & Error Handling

- Construction stays side-effect free, matching the existing rule that `--help` never
  touches the keyring, the config file, or the network.

---

### 6.10 Registration and lifecycle

**File(s):** `src/vidbyte_cli/commands/__init__.py`,
`src/vidbyte_cli/lib/runtime/application.py`
**Type:** Modified

#### What it does

Attaches the `research` group to the root program alongside `connect`, `harness`, and
`config`, and closes the invocation's HTTP client on every exit path.

#### Logic / Algorithm

1. `register_all_commands` builds a `click.Group(name="research", ...)`, registers the
   seven command classes on it, and adds it to the program — the identical shape used for
   the `connect` and `config` groups.
2. `CliApplication.run` wraps its existing try/except in a `finally` that calls
   `self._context.close()`.

#### Edge Cases & Error Handling

- Registration constructs no services, so `research --help` stays offline and the smoke
  suite can assert on it without credentials.
- `close()` in `finally` runs after the error handler has rendered, so a failure still
  reports before the pool is released.

---

### 6.11 Smoke coverage

**File(s):** `scripts/smoke.py`
**Type:** Modified

#### What it does

Adds credential-free contract cases for the new surface.

#### Logic / Algorithm

New `Case` rows:

- `research --help`, `research start --help`, `research add --help`,
  `research status --help`, `research watch --help`, `research threads --help` — all exit 0.
- `research add not-a-uuid "prompt"` — exit 2, `INVALID_ARGUMENT`. This is the load-bearing
  one: it proves the thread-id guard fires locally, before credential resolution, which is
  what keeps a pasted internal identifier from becoming a confusing 422.
- `research thread not-a-uuid` — exit 2, `INVALID_ARGUMENT`.

#### Edge Cases & Error Handling

- Every new case must fail *before* any credential is resolved, or it would exit 4 in the
  isolated smoke home instead of 2. Argument validation therefore runs first in the command
  callbacks.

---

## 7. Data Model Changes

**N/A — no persisted schema changes.** This PR adds no new file format, no new state
directory, and no migration. `lib/config/paths.py:56` `operations_dir()` remains unused;
see §13, Alternative 3 for why the operation journal that would have used it is out of
scope.

---

## 8. API Changes

No backend change. These are the routes the CLI now consumes. All are prefixed
`/api/v1/research`, authenticated with `x-api-key`, and return the DTO directly rather than
inside the `{success, data}` envelope. This section supersedes §8.1–§8.12 of
`docs/design/python-cli-research-harness-program.md`, which described a surface that was
never built.

### 8.1 POST /api/v1/research/run

**Change type:** New consumer. Scope `research:write`. Priced. Requires `Idempotency-Key`.

**Request:**
```json
{
  "prompt": "string - required, 1..20000 characters",
  "request_schema_version": "int - always 2",
  "size": "string|absent - small | medium | large",
  "target_sources": "int|absent - 1..1000",
  "search_calls": "int|absent - 1..100",
  "resource_kinds": "string[]|absent - paper | web, 1..2 entries",
  "include_domains": "string[]|absent - hostnames only",
  "exclude_domains": "string[]|absent - hostnames only",
  "published_after": "string|absent - YYYY-MM-DD",
  "language": "string|absent - 2..12 characters",
  "max_run_cost_cents": "int|absent - 1..100000"
}
```

**Response (202):**
```json
{
  "encrypted_id": "string - the public thread share token, a UUIDv4",
  "run_id": "string - the run identifier",
  "status": "string - admitting | accepted"
}
```

**Error cases:**

| Status | Condition |
|---|---|
| 401 | No credential, or a key the gatekeeper rejected |
| 402 | The account has insufficient credits for the run |
| 403 | The key authenticated but lacks `research:write` |
| 422 | Missing `Idempotency-Key`, or a request field failed validation |
| 429 | The weighted per-minute request budget is exhausted |
| 5xx | Backend unavailable |

### 8.2 POST /api/v1/research/threads/{encrypted_id}/run

**Change type:** New consumer. Identical request and response to §8.1.

**Error cases:** as §8.1, plus:

| Status | Condition |
|---|---|
| 404 | No active thread with that share token is owned by the caller |
| 422 | The path segment is not a UUIDv4 share token |

### 8.3 POST /api/v1/research/runs/{run_id}/continue

**Change type:** New consumer. No request body. Response identical to §8.1.

**Error cases:** as §8.1, plus:

| Status | Condition |
|---|---|
| 404 | No such run is owned by the caller |
| 409 | The run is not `partial`, `failed`, or `credit_exhausted` |

### 8.4 GET /api/v1/research/runs/{run_id}

**Change type:** New consumer. Scope `research:read`.

**Response (200):**
```json
{
  "run_id": "string",
  "thread_id": "string - the INTERNAL id; the CLI discards this field",
  "status": "string - admitting | accepted | running | completed | partial | failed | cancelled | credit_exhausted",
  "phase": "string - coarse execution phase",
  "continuation_count": "int - how many times this run was continued",
  "updated_at": "string - ISO 8601 timestamp"
}
```

**Error cases:** 401, 403 (missing `research:read`), 404, 429, 5xx.

### 8.5 GET /api/v1/research/portfolio

**Change type:** New consumer. Scope `research:read`. Query: `cursor` (1..128 chars),
`limit` (1..100, server default 20).

**Response (200):**
```json
{
  "threads": [
    {
      "encrypted_id": "string - the public share token the CLI shows as thread_id",
      "thread_id": "string - the INTERNAL id; the CLI discards this field",
      "title": "string",
      "run_count": "int",
      "source_count": "int",
      "artifact_count": "int",
      "latest_run_id": "string|null",
      "latest_run_status": "string|null",
      "created_at": "string - ISO 8601",
      "updated_at": "string - ISO 8601"
    }
  ],
  "next_cursor": "string|null - absent or null means the end of the collection"
}
```

**Error cases:** 401, 403, 422 (a cursor or limit outside its bounds), 429, 5xx.

### 8.6 GET /api/v1/research/threads/{encrypted_id}

**Change type:** New consumer. Scope `research:read`. Response is §8.5's row shape plus
`latest_run_phase` and `favorite`.

**Error cases:** 401, 403, 404 (missing, soft-deleted, or not owned), 422 (the path segment
is not a share token), 429, 5xx.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/research-production-api-surface.md` | This document |
| CREATE | `src/vidbyte_cli/lib/api/response.py` | Wire shapes and the bounded success decoder |
| CREATE | `src/vidbyte_cli/lib/api/retry.py` | Retry eligibility and bounded backoff |
| CREATE | `src/vidbyte_cli/lib/api/problem.py` | Status-driven failure classification |
| MODIFY | `src/vidbyte_cli/lib/api/client.py` | Replace the three `NotImplementedFeature` stubs with the real request path |
| CREATE | `src/vidbyte_cli/lib/api/endpoints/research.py` | Typed wrappers for the six research routes |
| CREATE | `src/vidbyte_cli/types/research.py` | Research wire models, status vocabulary, and the two identifier value classes |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | 15 new `CliError` subclasses (§6.8) |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | `require_credentials`, `api_client`, `research_endpoints`, `close` |
| MODIFY | `src/vidbyte_cli/lib/runtime/application.py` | Close the invocation's HTTP client in a `finally` |
| CREATE | `src/vidbyte_cli/commands/research/__init__.py` | Package marker for the new command group |
| CREATE | `src/vidbyte_cli/commands/research/options.py` | Shared run-request options for `start` and `add` |
| CREATE | `src/vidbyte_cli/commands/research/render.py` | Human and machine rendering for all four result shapes |
| CREATE | `src/vidbyte_cli/commands/research/start.py` | `research start` |
| CREATE | `src/vidbyte_cli/commands/research/add.py` | `research add` |
| CREATE | `src/vidbyte_cli/commands/research/resume.py` | `research resume` |
| CREATE | `src/vidbyte_cli/commands/research/status.py` | `research status` |
| CREATE | `src/vidbyte_cli/commands/research/watch.py` | `research watch` and its poll loop |
| CREATE | `src/vidbyte_cli/commands/research/threads.py` | `research threads` |
| CREATE | `src/vidbyte_cli/commands/research/thread.py` | `research thread` |
| MODIFY | `src/vidbyte_cli/commands/__init__.py` | Register the `research` group |
| MODIFY | `scripts/smoke.py` | Credential-free help and argument-guard cases |
| MODIFY | `README.md` | Document the `research` commands |

**Totals:** 17 created (1 doc + 16 source), 6 modified, 0 deleted.

Deliberately **not** created, against the side branch's plan: `features/research/{domain,
application,infrastructure,presentation}/*` (16 files), `lib/polling/*`,
`lib/operations/*`, `lib/runtime/clock.py`, `lib/runtime/signals.py`,
`commands/research/exports.py`, and every sources/artifacts/capabilities/exports model.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| `httpx` | `>=0.27,<1` (already declared) | Synchronous HTTP transport | None new; already a declared runtime dependency |
| `pydantic` | `>=2.6,<3` (already declared) | Request/response validation | Alias behaviour with `populate_by_name` off is load-bearing (§6.5) |
| `click` | `>=8.1,<9` (already declared) | Command registration and argument types | None new |
| Vidbyte API | `https://vidbyte-backend.onrender.com` (config default) | The six research routes | Backend schema drift surfaces as `ApiResponseUnsupported`; `extra="ignore"` absorbs additive fields |

No new package is added to `pyproject.toml`.

---

## 11. Rollout & Deployment

- **Feature flags:** none. The side branch gated the group behind
  `VIDBYTE_EXPERIMENTAL_RESEARCH`; that gate existed because the routes were speculative.
  They are in production, so the group ships on.
- **Breaking change:** no. Every added command is new. The one behavioural change to
  existing surface is that `ApiClient.get`/`get_list`/`post` now perform a request instead
  of raising `NotImplementedFeature` — which only affects `AuthEndpoints` and
  `HarnessEndpoints`, whose sole caller is `HarnessContext.harness_endpoints()`, itself
  reached only from harness `dispatch` paths that are still unimplemented.
- **Deployment order:** none. The backend already exposes every route consumed here.
- **Rollback:** revert the PR. No persisted state is written, so there is nothing to
  migrate back.

---

## 12. Open Questions

- [ ] Should the CLI surface the backend's `incident_id` from the error body? It is a
      stable UUID, not prose, and it is what support would ask for. Deferred because
      reading it means parsing an error body, and the field guide's rule is that failure
      prose stays static authored text. The `x-request-id` header is used instead where the
      backend sets one.
- [ ] Does the production deployment set an `x-request-id` response header? Unverified. If
      it does not, `request_id` is simply absent from every failure, which the renderer
      already handles.
- [ ] Which spend tier a given API key lands on is not visible to the CLI, so the 10-second
      poll floor is sized for the worst case (30 weighted requests/minute). If a
      per-key rate hint ever appears in a response header, `watch` should read it.
- [ ] `include_domains` is checked against a server-side reviewed allowlist
      (`ResearchIncludeDomain.validated`) the CLI cannot see, so an unreviewed domain is a
      422 that costs a round trip. Acceptable until the allowlist is published.

---

## 13. Alternatives Considered

### Alternative 1: Merge or rebase `feat/research-api-wiring`

- **What:** Bring the side branch forward wholesale.
- **Why rejected:** It is ~6,400 lines diverged from `main` and conflicts with PRs #11–#14
  across errors, config, auth, and runtime. Taking the stale side of those conflicts would
  silently revert three merged review-fix PRs — the exact failure the field guide's
  "porting a stale stacked PR is a rewrite" rule documents. Roughly 40% of the branch
  implements routes that do not exist.

### Alternative 2: Keep the branch's five-layer feature structure

- **What:** `features/research/{domain,application,commands,infrastructure,presentation}`,
  16 files with ports, adapters, and a gateway protocol.
- **Why rejected:** That structure buys insulation from an unknown backend contract. The
  contract is now known and stable, and every port would have exactly one implementation.
  `main`'s own grain — `types/`, `lib/api/endpoints/`, `commands/<group>/` — carries the
  same feature in 10 files with no indirection a reader has to step through.

### Alternative 3: Journal every mutation locally before sending it

- **What:** `lib/operations/{journal,idempotency,recorder}.py` writing a schema-versioned
  `PendingOperation` file per mutation into `paths.operations_dir()`, so an interrupted
  `start` could be replayed under its original idempotency key.
- **Why rejected:** This was in the handoff context for this work and I am deliberately
  departing from it. The journal only pays off inside a narrow window — the process dying
  after the POST is written but before the response is decoded — and in that window the
  thread already exists and `research threads` finds it. Against that it adds three
  modules, a new persisted schema, and a state directory that grows without bound and has
  no eviction path. `--idempotency-key` on the three mutation commands, plus reporting the
  key used in the machine document, gives an agent full control over replay with none of
  that. **This flips if** a recovery command that replays by operation id is ever asked
  for; then the journal is the right home for it.

### Alternative 4: Generic `lib/polling/Poller` with a `PollTarget` protocol

- **What:** The side branch's reusable poller, adapted by a research target class.
- **Why rejected:** One caller, one implementation. The program document anticipated
  generic harness waiting as a second caller, but that is unimplemented, so the abstraction
  would be shaped by a single use case and then have to change when the second arrives.
  The loop lives as four private methods on `ResearchWatchCommand` until there is a second
  caller to shape it.

### Alternative 5: `CancellationSignal` and a `SignalScope` handler

- **What:** Install SIGINT/SIGTERM handlers that set cooperative cancellation state which
  the poll loop and the request loop check.
- **Why rejected:** `ErrorHandler.handle` already matches `KeyboardInterrupt` and returns
  `OperationInterrupted` at exit 130, and that failure's description already states that
  submitted work is not cancelled by the signal. The machinery would replace a working
  path with an equivalent one, and installing process signal handlers in a library that
  can be embedded is a cost with no matching benefit here.

### Alternative 6: Surface both identifiers and label them

- **What:** Print `thread_id` and `share_id` side by side and let the user pick.
- **Why rejected:** The internal identifier is useful to nobody outside the backend, and
  publishing it makes every documentation example ambiguous about which one to paste. The
  cost of hiding it is that `status` cannot tell a user where to add more work — acceptable,
  because `start` and `threads` are the only places a thread id is minted and both print
  it prominently. **This flips if** `ResearchRunStatusDto` ever gains `encrypted_id`.

### Alternative 7: Derive the idempotency key from a hash of the request body

- **What:** Identical prompts automatically share a key, so an accidental re-run is free.
- **Why rejected:** Already settled as Alternative 9 of the program document — a user may
  intentionally run the same research twice, and content-derived keys make that impossible
  without an escape hatch. A fresh `uuid4()` per invocation with an explicit override is
  the behaviour the program committed to.

### Alternative 8: Add `--wait` to `start`, `add`, and `resume`

- **What:** Block after admission until the run settles.
- **Why rejected:** Not required by the acceptance criteria, and `research watch <run_id>`
  already composes with the run id every mutation prints. Deferred as a follow-up rather
  than expanding three commands for a behaviour one command already provides.

### Alternative 9: Add `--exit-status` so terminal outcomes set the shell status

- **What:** Map `partial` to exit 3, `credit_exhausted` to 5, `failed` to 1.
- **Why rejected:** Honouring a command's return value requires changing
  `CliApplication._invoke`, which currently discards Click's return and always returns 0 —
  a root-runtime change well beyond this PR's scope. The terminal status is in both the
  human and the JSON output, so a shell can branch on it today. Carried as a follow-up.

### Alternative 10: Parse the backend error body to classify failures

- **What:** Branch on the `code` field of `{"error", "title", ..., "code", "incident_id"}`.
- **Why rejected:** The field guide requires failure prose to be static authored text
  independent of backend response content. Status-code classification produces the same set
  of user-facing outcomes on this surface, since each status has exactly one meaning here.
  The cost is losing `incident_id`; see §12.

---

## Verification

The canonical gate, recorded here per the field guide so it is not re-derived:

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

`run_ci.py` covers ruff lint, ruff format, mypy strict, `compileall`, the offline smoke
suite, an isolated sdist/wheel build, `twine check`, and a clean-virtualenv wheel install
that proves imports resolve from the artifact. Line length is 100 and `ruff format` will
not split a long call chain for you.

Manual verification against production, outside CI, once a live key is available:

1. `vidbyte-cli research start "..."` returns a thread id and a run id.
2. `vidbyte-cli research add <that thread id> "..."` is accepted verbatim.
3. `vidbyte-cli research threads` lists the thread under the same id.
4. `vidbyte-cli research status <run id>` and `watch` print no id that cannot be pasted.
5. `vidbyte-cli research resume <a running run id>` fails with the resume rule stated.
