# Design Doc: Login Key Verification

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-14
**Last Updated:** 2026-08-14

---

## 1. Overview

`vidbyte-cli login` already refuses to write a key it has not verified — `LoginCommand.execute`
calls `CredentialVerifier.verify` on the line immediately before the only call to
`CredentialStore.write`. What is missing is a verifier that can actually ask Vidbyte. Today the
bound implementation is `PendingCredentialVerifier`, which raises unconditionally, so **no login
can ever succeed in this build**. This change supplies the real one: it implements HTTP in
`ApiClient`, points it at `POST /api/skills/auth/validate` — the only permission-free liveness
check the backend serves today — and wires that same call into `vidbyte-cli whoami`, which
currently raises `NotImplementedFeature`. A key reaches durable storage only after the server
has accepted it, and `whoami` reports a non-secret identity derived from the same check.

---

## 2. Goals & Non-Goals

### Goals

- Implement real HTTP request execution in `ApiClient` for the one operation this feature needs.
- Replace `PendingCredentialVerifier` with `ApiCredentialVerifier`, backed by a route that
  exists on the deployed backend today.
- Preserve the existing verify-before-persist ordering in `LoginCommand.execute` without
  restructuring it.
- Implement `vidbyte-cli whoami` using the same check, printing a non-secret identity.
- Distinguish "I could not reach Vidbyte" from "Vidbyte rejected this key" as separate typed
  failures with separate exit codes.
- Never write, log, echo, or serialize a rejected key, a valid key, or the `session_token` the
  backend returns.

### Non-Goals

- **No backend changes.** This repository implements no routes. `/api/skills/auth/validate` is
  consumed exactly as it exists at `backend/routes/skills.py:184`.
- **No capability or permission checking at login.** Login answers "is this key alive?", not
  "can this key do X". See §14 Alternative 2 for why.
- **No retry, backoff, idempotency, polling, or operation journal.** Those are PR 4 of
  `docs/design/python-cli-research-harness-program.md` and are deliberately excluded.
- **No implementation of `ApiClient.get`, `get_list`, or `post`.** Those three carry envelope
  semantics against `/harness/*` routes that do not exist server-side yet; implementing them
  now would be inventing an API. They keep raising `NotImplementedFeature`.
- **No `/auth/whoami` route.** It does not exist. See §3.
- **No change to `Credentials.is_live_format`** or the `vb_live_`-only narrowing that landed in
  PR #14, even though the backend also accepts `vb_test_`. Noted in §13.
- **No caching of the verification result** across invocations.

---

## 3. Background & Context

### Why now

`main` is at `1c8bcc0` ("aim the CLI at the live Vidbyte API with a live-key x-api-key header",
PR #14, merged during this audit). That PR gave `ApiClient` its constructor
`(config: ResolvedConfig, credentials: Credentials)` and its `auth_headers()` method, and taught
both input boundaries to reject a non-`vb_live_` token. It stopped exactly short of sending a
request. The CLI can now build a correct authenticated request and has nothing that sends one.

### Current state, verified in the code

`src/vidbyte_cli/commands/auth/login.py:52-63`:

```python
# Verify-before-persist. Syntactic checks cannot prove a key authenticates, and this
# call sits immediately before the only write so a reordering is obvious in review.
context.credential_verifier().verify(credentials, config)
fallback_allowed = self._fallback_consent(context, allow_file_fallback)
context.migration().migrate_if_needed()
storage = context.credential_store().write(...)
```

The invariant is already enforced and already commented. `src/vidbyte_cli/lib/auth/verifier.py:27`
is what blocks it:

```python
class PendingCredentialVerifier:
    """Explicit seam completed by the reusable HTTP platform."""

    def verify(self, credentials: Credentials, config: ResolvedConfig) -> None:
        del credentials, config
        raise CredentialVerificationUnavailable()
```

`ApplicationContext.__init__` binds it at `lib/runtime/context.py:74`:
`self._verifier_factory = verifier_factory or PendingCredentialVerifier`.

### Why not the side branch's approach

`feat/research-api-wiring` contains a finished `ApiCredentialVerifier` that calls
`AuthEndpoints(client).whoami()` → `GET /auth/whoami`. **That route does not exist.**
`backend/app.py:89-110` registers every router and none owns `/auth/*`. Worse than a 404: the
path is absent from `_API_KEY_ONLY_ROUTE_PERMISSIONS` in `backend/middleware/api_platform.py:40-57`,
so `AuthHeaderMiddleware` never enters its API-key branch and the request falls through to JWT
handling, returning a 401 about bearer tokens. The CLI would report "invalid key" when the
actual problem is a missing route. `docs/design/live-api-host-and-key-header.md:662` reached the
same conclusion independently.

### Why not a cheap research read

There are no research or harness routes on the backend. `grep -rn harness backend/**/*.py`
matches two test scripts and nothing else. `/harness/run`, `/harness/get/{id}`,
`/harness/catalog`, and `/harness/{name}/manifest` — the paths `HarnessEndpoints` targets — are
all client-side fiction today. Verifying against one means building it first.

### The route that does exist

`POST /api/skills/auth/validate`, `backend/routes/skills.py:184`. It is listed as
`PublicSkillRoute.AUTH_VALIDATE`, so `AuthHeaderMiddleware` skips it entirely
(`backend/middleware/auth.py:196-200`) and the handler performs its own lookup: format check →
`derive_api_key_hash` → `_resolve_key_principal` → explicit REVOKED / DISABLED / EXPIRED checks.
No permission scope is consulted anywhere in that path. That property is the whole reason it is
the right choice, and §14 Alternative 2 explains why a resource read is not.

### Constraints discovered in the backend

1. **Rate limit: 5 per IP per 15 minutes** (`AUTH_IP_15MIN_LIMIT` in
   `backend/lib/config/skills.py:26`), plus 100 globally per 15 minutes, plus a circuit breaker.
   This is the single most important operational constraint in this design. See §4 NFR-4 and §13.
2. **It writes.** `create_skill_session` (`backend/database/queries/skills.py:149`) inserts a
   session document per call. Bounded by a TTL index on `expires_at` with
   `expireAfterSeconds: 0` (`backend/lib/database/index.py:30`) and `SESSION_TTL_DAYS = 30`.
3. **It returns a live credential.** The 200 body includes `session_token`, a 30-day skills
   session. The CLI must never model, store, log, or print it.
4. **CORS and IP intelligence pass for a CLI.** `enforce_cors`
   (`backend/lib/middleware/skills_requests.py:46-50`) returns `None` when there is no `Origin`
   header, which is the CLI case. `enforce_ip_intelligence`
   (`backend/lib/middleware/skills_security.py:294-313`) on this path only rejects
   already-blocked IPs; the bot scorer that can block an IP for 24 hours runs on the skill POST
   paths, not on `auth/validate`.
5. **The identity is thin.** `backend/routes/skills.py:279-281` sets
   `username=principal.user_id`, `email=principal.user_id`, and `account_tier="free"` is
   hardcoded at line 281. There is no `user_id` key in the response. The CLI can honestly
   report `username` and `account_tier` and must not present `email` as an email.

### Repo conventions that bind this change

Read from `field-guide/vidbyte-cli/`:

- Every failure is a `CliError` subclass in `lib/errors/failures.py` with its own
  `message`/`description`/`trace`/`hint`. Never a bare `CliError(...)`. Never a module-level
  error-constructor function.
- `description` is 3–4 sentences; `trace` is a semantic path description, not a stack dump;
  `file_path` is derived by `CliError._origin_file()` and never hand-written; `cause` is private
  and never serialized.
- No templated `PURPOSE` / `FUNCTION INVENTORY` / `WHAT NOT TO DO` headers. A 3–6 line module
  docstring, then sparse comments on non-obvious invariants only.
- No function may sit alone at the end of a module.
- A stateless single-use helper is a private method, not a collaborator class.
- Switch/`match` over an if/else ladder when branching on one value.
- The verification gate is `python scripts/run_ci.py`. Line length 100, mypy strict.

---

## 4. Requirements

### Functional Requirements

1. `LoginCommand.execute` MUST call the credential verifier before `CredentialStore.write`, and
   the existing call ordering at `login.py:52-63` MUST NOT change.
2. When the backend accepts the key (HTTP 200 with `success: true`), login MUST proceed to
   storage exactly as it does today, including the keyring-first/consent-gated fallback.
3. When the backend rejects the key (HTTP 401 or 403), login MUST fail and MUST NOT write to the
   OS keyring, the restricted fallback file, or the legacy path.
4. When the backend cannot be reached (DNS failure, connection refused, connect timeout, read
   timeout, TLS failure), login MUST fail with a **different** typed failure than rejection, and
   MUST NOT write anything.
5. When the backend returns 5xx, login MUST fail closed — no optimistic storage.
6. When the backend returns a response the CLI cannot decode (non-JSON content type, oversized
   body, malformed JSON, schema mismatch, `success: false` on a 200), login MUST fail with an
   `API_PROTOCOL_ERROR` and MUST NOT write anything.
7. The verification request MUST send the key in the `x-api-key` header and in no other header,
   no query parameter, and no request body.
8. The verification request MUST NOT follow redirects, so the `x-api-key` header can never be
   replayed to a host the caller did not configure.
9. The request path MUST be validated as a relative path beginning with `/`; an absolute URL or
   a scheme-relative path supplied by an endpoint group MUST be rejected before any socket is
   opened.
10. The verification POST MUST NOT be retried. It has a server-side write side effect
    (`create_skill_session`) and a 5-per-15-minute budget.
11. `vidbyte-cli whoami` MUST resolve the stored credential through `CredentialResolver`, run the
    same verification call, and print `username`, `account_tier`, the profile, the API URL, and
    the credential source.
12. `vidbyte-cli whoami` with no stored credential MUST fail with `AUTH_REQUIRED` / exit 4 and
    MUST NOT make a network call.
13. Neither the API key nor the returned `session_token` may appear in any output stream, any
    `OutputDocument`, any error `message`/`description`/`trace`/`hint`, or any debug traceback.
14. `PendingCredentialVerifier` and `CredentialVerificationUnavailable` MUST be removed. Once a
    real verifier exists, a class whose only behavior is to fail closed is a dead path that will
    never execute again.
15. A 429 MUST surface as a retryable failure whose hint carries the server's `Retry-After`
    value when present, because the 5-per-15-minute budget makes this reachable in normal use.
16. Importing `vidbyte_cli` or `vidbyte_cli.cli` MUST NOT import `httpx`.

### Non-Functional Requirements

- **NFR-1 Startup cost.** `vidbyte-cli --version` currently runs in ~0.23 s and already imports
  `click`, `keyring`, and `pydantic`. A cold `import httpx` measures ~0.14 s on this machine, a
  ~60% regression on the hot path that agents call constantly. `httpx` MUST therefore be
  imported inside the method that performs the request, not at module scope. FR16 is the
  enforceable form of this and is checked by `scripts/smoke.py`.
- **NFR-2 Bounded input.** The response body MUST be size-bounded before JSON parsing, matching
  the existing pattern (`_MAX_CREDENTIAL_BYTES`, `_MAX_TOKEN_CHARACTERS`,
  `_MAX_KEY_CHARACTERS`). Limit: 1 MiB, ample for a five-field object.
- **NFR-3 Timeout.** The request MUST use `ResolvedConfig.request_timeout_seconds` (validated
  `ge=1.0, le=300.0`, default 30.0). No unbounded wait is acceptable — a hung TLS handshake
  would otherwise block `login` forever with a secret held in memory.
- **NFR-4 Rate-limit legibility.** Because the budget is 5 per IP per 15 minutes, a 429 must
  produce a message a user can act on rather than a generic failure. This is a documentation and
  error-wording requirement, not a retry requirement.
- **NFR-5 Observability.** Every API failure carries `request_id` when the response supplies one,
  so a support ticket can be correlated. `request_id` is already a first-class `CliError` field
  rendered in both human and machine output.
- **NFR-6 Secret hygiene.** `Credentials.secret_value()` is unwrapped in exactly one place,
  `ApiClient.auth_headers()`, which already exists and is already commented as such. This change
  adds no second unwrapping site.

---

## 5. High-Level Design

The change is deliberately small: **one class becomes real, one method gains a body, one command
stops raising.** No new packages, no new layers, no new abstractions with a single implementation.

`ApiClient` gains one public method, `post_direct`, and four private ones that compose into it.
`post_direct` performs an authenticated POST with no body and validates an **unwrapped** JSON
object into a pydantic model. Unwrapped is the operative word: `/api/skills/auth/validate` returns
a bare object, not the `{success, message, data}` `ApiEnvelope` that `types/api.py` describes for
`/harness/*`. The three existing methods (`get`, `get_list`, `post`) carry envelope semantics
against routes that do not exist yet and keep raising `NotImplementedFeature`.

`ApiClient` classifies failures by **HTTP status only**. It does not read the backend's `code`
field. The backend serves three mutually incompatible error shapes today —
`{error, code, message, request_id}` from skills routes, `{error, title, subtitle}` from
`AuthHeaderMiddleware._api_key_error_response`, and `{code, title, detail}` from
`PublicApiResponseFactory` — so `code` is not a platform contract and a generic client that
special-cased the skills spelling would be wrong the moment `/harness/*` lands. The cost is that
the four distinct 401 reasons (invalid, revoked, disabled, expired) collapse into one failure;
that failure's `description` enumerates all four, and the user's next action is identical in
every case. §14 Alternative 4 records the condition that flips this.

`ApiCredentialVerifier` replaces `PendingCredentialVerifier`. It constructs an `ApiClient` from
the invocation's `ResolvedConfig` and the candidate `Credentials`, calls
`AuthEndpoints.validate()`, and returns the decoded `KeyIdentity`. The `CredentialVerifier`
protocol changes its return type from `None` to `KeyIdentity` so that `whoami` and `login` share
one call — login discards the identity, `whoami` prints it. That is the literal reading of "'who
am I?' uses that same check".

```
vidbyte-cli login                          vidbyte-cli whoami
      |                                          |
CredentialInput.read  (prompt/stdin)      CredentialResolver.resolve  (env/keyring/file)
      |                                          |            -> None: AuthenticationRequired (no network)
      +--------------------+---------------------+
                           |
              ApplicationContext.credential_verifier()
                           |
                 ApiCredentialVerifier.verify(credentials, config)
                           |
                    AuthEndpoints.validate()
                           |
              ApiClient.post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
                           |
              _url -> _send (httpx, no redirects, timeout)
                           |
            +--------------+---------------+
            | 2xx                          | non-2xx / transport error
       _decode (bounded)             _failure_for_status  /  ApiUnreachable
            |                              |
       KeyIdentity                    raise CliError subclass
            |                              |
   login: CredentialStore.write       nothing written, exit 1/2/4
   whoami: print identity
```

The key design decisions and their reasons:

**Only the one operation this feature needs is implemented.** A generic `request()` with
`response_shape`, retry policy, and idempotency is PR 4's contract. Building it now against one
real route and four imaginary ones would be speculative.

**No `lib/api/problem.py` or `lib/api/response.py`.** The side branch has both. Their structure
is right and this design follows it, but as private methods on `ApiClient` rather than separate
files: `ApiProblemMapper` and `ResponseDecoder` are stateless with one caller each, and the field
guide's restraint rule is explicit that such a helper is a private method, not a collaborator
class. Six small methods on one cohesive class beats three files.

**`httpx` is imported inside `_send`.** Measured: it costs 0.14 s on a 0.23 s `--version`. This
is the one place in the design where an unusual construct is chosen deliberately, and it carries
a comment saying why.

---

## 6. Detailed Design

### 6.1 ApiClient

**File(s):** `src/vidbyte_cli/lib/api/client.py`
**Type:** Modified

#### What it does

Owns transport, bounded decoding, and status-driven failure classification for one authenticated
request. It resolves nothing — host, timeout, and secret all arrive already validated.

#### Interface / API

```python
API_KEY_HEADER_NAME = "x-api-key"          # unchanged, already on main
_MAX_RESPONSE_BYTES = 1_048_576            # new
_JSON_MEDIA_TYPE = "application/json"      # new

class ApiClient:
    def __init__(self, config: ResolvedConfig, credentials: Credentials) -> None: ...
    def auth_headers(self) -> dict[str, str]: ...                                  # unchanged

    def post_direct(self, path: str, model: type[TModel]) -> TModel:
        # POSTs with no body and validates the response object itself, not an envelope's `data`.

    def get(self, path: str, model: type[TModel]) -> TModel: ...                   # still raises
    def get_list(self, path: str, model: type[TModel]) -> list[TModel]: ...        # still raises
    def post(self, path: str, body: BaseModel, model: type[TModel]) -> TModel: ... # still raises

    def _url(self, path: str) -> str:
        # Joins a validated relative path onto the origin; rejects anything that could retarget.

    def _send(self, url: str) -> httpx.Response:
        # Executes the POST with the invocation timeout and redirects disabled.

    def _decode(self, response: httpx.Response, model: type[TModel]) -> TModel:
        # Content-type, size, and schema checks before typed data crosses the boundary.

    def _failure_for_status(self, response: httpx.Response) -> CliError:
        # Maps one HTTP status onto a typed failure, without reading response prose.

    def _request_id(self, response: httpx.Response) -> str | None:
        # Reads a bounded correlation id from the response headers.
```

#### Logic / Algorithm

`post_direct`:

1. `url = self._url(path)`.
2. `response = self._send(url)` — raises `ApiUnreachable` on any transport error.
3. If `response.status_code` is not in the 200–299 range, `raise self._failure_for_status(response)`.
4. `return self._decode(response, model)`.

`_url`:

1. Reject the path unless it starts with `/` and does not start with `//` (protocol-relative).
2. Reject any path containing `://`.
3. On rejection raise `ApiRequestPathInvalid` — a CLI defect, not a user mistake, but it must be
   a hard stop because the failure mode it prevents is sending `x-api-key` to a foreign host.
4. Return `f"{self.base_url}{path}"`. `ApiOrigin.parse` already guarantees `base_url` carries no
   path, no query, no fragment, and no userinfo, so plain concatenation is correct here.

`_send`:

1. `import httpx` locally, with the NFR-1 comment.
2. `with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:` —
   `follow_redirects=False` is httpx's default and is set explicitly because it is load-bearing
   (FR8).
3. `return client.post(url, headers={**self.auth_headers(), "Accept": _JSON_MEDIA_TYPE})`.
4. Catch `httpx.HTTPError` (the base class covering timeouts, connect errors, protocol errors)
   and `raise ApiUnreachable(error) from error`.

`_decode`:

1. `content = response.content`.
2. If `len(content) == 0` or `> _MAX_RESPONSE_BYTES` → `ApiProtocolError`.
3. Media type from `content-type` header, split on `;`, lowered. Accept `application/json` or a
   `+json` suffix; anything else → `ApiProtocolError`. This is what catches a proxy's HTML error
   page arriving with a 200.
4. `json.loads(content)`; `UnicodeDecodeError` or `JSONDecodeError` → `ApiProtocolError`.
5. `model.model_validate(payload)`; `ValidationError` → `ApiProtocolError`.
6. Return the model. Note the `success` check does **not** live here — it is a field on
   `KeyIdentity` (§6.3) and is enforced by the verifier (§6.4), because "success" is the skills
   route's vocabulary, not the transport's.

`_failure_for_status` — a `match` on `response.status_code`, per house style:

| Status | Failure | Code | Exit |
|--------|---------|------|------|
| 401, 403 | `ApiCredentialRejected` | `AUTH_REQUIRED` | 4 |
| 400, 409, 422 | `ApiRequestRejected` | `INVALID_ARGUMENT` | 2 |
| 404 | `ApiRouteMissing` | `API_UNAVAILABLE` | 1 |
| 429, 500–599 | `ApiTemporarilyUnavailable` | `API_UNAVAILABLE` | 1, retryable |
| anything else | `ApiOperationFailed` | `OPERATION_FAILED` | 1 |

`ApiTemporarilyUnavailable` reads the `Retry-After` header and folds it into its hint when it is
a plausible integer (FR15).

#### Edge Cases & Error Handling

- **Empty body with 200** → `ApiProtocolError`, nothing stored. Silent-failure guard: an empty
  body would otherwise validate as `{}` under a permissive model.
- **204 No Content** → caught by the empty-body check, `ApiProtocolError`.
- **Body exactly at the 1 MiB bound** → accepted; one byte over → rejected. Compared against the
  materialized body rather than the declared `content-length`, because `content-length` is absent
  under chunked transfer encoding.
- **`content-type: text/html` with 200** → `ApiProtocolError`. This is the captive-portal and
  reverse-proxy case, and without the check a login could "succeed" against a Wi-Fi login page.
- **3xx** → not followed. Falls into `_failure_for_status`'s default arm as
  `ApiOperationFailed`. The header is never re-sent.
- **A path that is an absolute URL** → `ApiRequestPathInvalid` before any socket opens.
- **Timeout mid-read** → `httpx.ReadTimeout` is an `httpx.HTTPError` → `ApiUnreachable`, which is
  the failure that must not be confused with rejection (FR4).

### 6.2 AuthEndpoints

**File(s):** `src/vidbyte_cli/lib/api/endpoints/auth.py`
**Type:** Modified

#### What it does

Names the one authentication route the CLI calls and its response type. Replaces the `whoami()`
wrapper around the nonexistent `GET /auth/whoami`.

#### Interface / API

```python
# The permission-free liveness check. Chosen over a resource read because a key scoped only to
# write must still be able to log in; capability is enforced at the point of use, not here.
AUTH_VALIDATE_PATH = "/api/skills/auth/validate"


class AuthEndpoints:
    def __init__(self, client: ApiClient) -> None: ...

    def validate(self) -> KeyIdentity:
        # POST /api/skills/auth/validate — proves the configured key is live and returns identity.
        return self._client.post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
```

The path is a module constant rather than a one-member enum, matching the repo's actual practice
for this kind of value (`API_KEY_HEADER_NAME` in `client.py:25`, `LIVE_API_KEY_PREFIX` in
`credentials.py:36`, `DEFAULT_API_URL` in `config/models.py:22`).

#### Edge Cases & Error Handling

None of its own; every failure originates in `ApiClient`.

### 6.3 KeyIdentity

**File(s):** `src/vidbyte_cli/types/api.py`
**Type:** Modified — `WhoAmI` deleted, `KeyIdentity` added

#### What it does

The non-secret half of a successful validation. Deliberately does not model `session_token` or
`email`.

#### Interface / API

```python
class KeyIdentity(BaseModel):
    """Non-secret identity behind a validated key.

    `extra="ignore"` is deliberate and is the one place in this package that departs from the
    repo's `extra="forbid"` default: the 200 body also carries a live 30-day `session_token`
    this CLI has no use for, and ignoring it keeps it out of every modelled field, every
    `OutputDocument`, and every log line. `email` is dropped for a different reason — the
    backend sets it to the user id, so presenting it as an email would be a lie.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    success: bool
    username: str = Field(min_length=1, max_length=256)
    account_tier: str = Field(min_length=1, max_length=64)
```

`success` is modelled rather than ignored so that a 200 carrying `success: false` is a detectable
protocol violation instead of a silent pass (§6.4 step 3).

The `ApiEnvelope`, `ApiError`, and `ApiPagination` models in the same file are untouched — they
describe the `/harness/*` contract that PR 4 will consume.

### 6.4 ApiCredentialVerifier

**File(s):** `src/vidbyte_cli/lib/auth/verifier.py`
**Type:** Modified — `PendingCredentialVerifier` deleted, `ApiCredentialVerifier` added

#### What it does

The verify-before-persist boundary, now with a body. One method, used identically by `login` and
`whoami`.

#### Interface / API

```python
class CredentialVerifier(Protocol):
    def verify(self, credentials: Credentials, config: ResolvedConfig) -> KeyIdentity: ...


class ApiCredentialVerifier:
    """Prove a candidate key against the backend before it may be persisted."""

    def verify(self, credentials: Credentials, config: ResolvedConfig) -> KeyIdentity:
        # Calls the permission-free liveness check and returns the non-secret identity.
```

The protocol's return type changes from `None` to `KeyIdentity`. `LoginCommand` ignores the
return value; `WhoamiCommand` prints it.

#### Logic / Algorithm

1. `client = ApiClient(config, credentials)`.
2. `identity = AuthEndpoints(client).validate()`.
3. If `identity.success` is falsy, raise `ApiProtocolError` — a 200 that denies success is a
   contract the CLI cannot act on, and treating it as acceptance would store a key the server
   just refused.
4. Return `identity`.

`verifier.py` imports `ApiClient` at module scope. That is safe for FR16 because `httpx` is
imported inside `ApiClient._send`, not at `client.py`'s module scope.

#### Edge Cases & Error Handling

Every failure propagates unchanged from `ApiClient`. The verifier adds exactly one check of its
own (step 3), because `success` is skills-route vocabulary that the transport layer should not
know about.

### 6.5 LoginCommand

**File(s):** `src/vidbyte_cli/commands/auth/login.py`
**Type:** Unmodified

Listed explicitly because it is the feature's subject and the temptation to restructure it is
real. It already does the right thing. The only reason its behavior changes is that
`context.credential_verifier()` now returns a different object. **Zero lines change in this
file.**

### 6.6 WhoamiCommand

**File(s):** `src/vidbyte_cli/commands/auth/whoami.py`
**Type:** Modified — currently raises `NotImplementedFeature`

#### Interface / API

```python
class WhoamiCommand:
    def register(self, parent: click.Group) -> None: ...

    def execute(self, context: ApplicationContext) -> None:
        # Reads the stored credential, proves it with the same check login uses, prints identity.
```

#### Logic / Algorithm

1. `config = context.resolved_config()`.
2. `credential = context.credential_resolver().resolve(config.profile, config.api_url)`.
3. If `credential is None`, `raise AuthenticationRequired()`. **Before any network call** (FR12).
4. `identity = context.credential_verifier().verify(credential.credentials, config)`.
5. Emit `OutputDocument(kind="auth.whoami", data={...})` with `profile`, `api_url`, `username`,
   `account_tier`, `credential_source`. No secret, no `session_token`, no `email`.
6. Human line: `Authenticated as '<username>' (<account_tier>) on profile '<profile>'.`

`whoami` reads through `CredentialResolver`, so `VIDBYTE_API_KEY` outranks the keyring — which is
correct, since that is the key later commands would actually use. `login` deliberately does not
resolve through it (`lib/auth/resolver.py:7-8`), and that asymmetry stays.

#### Edge Cases & Error Handling

- No credential → `AuthenticationRequired` (exit 4), no network call.
- `VIDBYTE_API_KEY` set but empty/oversized → `InvalidEnvironmentApiKey` from the resolver, before
  any network call.
- Stored key that the backend now rejects → `ApiCredentialRejected` (exit 4). This is the useful
  case: `whoami` becomes the way to discover a revoked key.
- Offline → `ApiUnreachable` (exit 1, retryable), distinct from rejection.
- 429 → `ApiTemporarilyUnavailable`. Reachable after five `whoami` calls in 15 minutes; see §13.

### 6.7 ApplicationContext

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

One import and one line:

```python
self._verifier_factory = verifier_factory or ApiCredentialVerifier
```

The `verifier_factory` injection point (line 61) is unchanged and remains the seam a test or an
embedding process uses.

### 6.8 Failure classes

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

`CredentialVerificationUnavailable` is deleted (FR14). Seven classes are added, each carrying its
own `message`, 3–4 sentence `description`, semantic `trace`, and `hint`, per the field guide.
Every one is reachable on `/api/skills/auth/validate`; none is speculative.

| Class | Code | Exit | Retryable | Reached by |
|-------|------|------|-----------|------------|
| `ApiUnreachable` | `API_UNAVAILABLE` | 1 | yes | any `httpx.HTTPError` |
| `ApiCredentialRejected` | `AUTH_REQUIRED` | 4 | no | 401, 403 |
| `ApiRequestRejected` | `INVALID_ARGUMENT` | 2 | no | 400, 409, 422 |
| `ApiRouteMissing` | `API_UNAVAILABLE` | 1 | no | 404 |
| `ApiTemporarilyUnavailable` | `API_UNAVAILABLE` | 1 | yes | 429, 5xx |
| `ApiOperationFailed` | `OPERATION_FAILED` | 1 | no | any other status, incl. 3xx |
| `ApiProtocolError` | `API_PROTOCOL_ERROR` | 1 | no | undecodable 2xx |
| `ApiRequestPathInvalid` | `INTERNAL_ERROR` | 70 | no | a malformed path from an endpoint group |

`ApiRequestPathInvalid` is `INTERNAL_ERROR` / exit 70 because only CLI code constructs paths; a
bad one is a defect, not an invocation mistake.

`ApiCredentialRejected`'s `description` enumerates the four backend reasons (unknown, revoked,
disabled, expired) that the status-only mapping collapses, so the user still learns what to
check. Its `hint` points at the dashboard.

`AuthenticationRequired`'s `trace` is reworded from the harness-only path to cover both callers.
Its `code` and `exit_status` are unchanged, so the machine contract holds; `codes.py:5` explicitly
sanctions prose improvement while identity stays fixed.

### 6.9 Package exports and docs

**File(s):** `src/vidbyte_cli/lib/auth/__init__.py`, `src/vidbyte_cli/lib/auth/README.md`,
`src/vidbyte_cli/lib/api/README.md` (new), `README.md`
**Type:** Modified / New

`lib/auth/__init__.py` swaps `PendingCredentialVerifier` for `ApiCredentialVerifier` in both the
import and `__all__`.

`lib/auth/README.md:8-10` currently says "The HTTP-backed verifier lands with the reusable
networking platform in PR 4; this PR leaves a safe, non-persisting seam." That is now false and
is rewritten.

`lib/api/` has no README; every other `lib/*` package does. One is added describing the
transport boundary, the status-only classification decision, and the httpx import placement.

### 6.10 Smoke coverage

**File(s):** `scripts/smoke.py`
**Type:** Modified

`IMPORT_BOUNDARY_CODE` currently asserts `import vidbyte_cli` pulls in neither `click` nor
`httpx`. A second boundary is added for `vidbyte_cli.cli`, which is the import the hot path
actually pays and the one NFR-1 protects:

```python
CLI_IMPORT_BOUNDARY_CODE = (
    "import sys; import vidbyte_cli.cli; assert 'httpx' not in sys.modules"
)
```

Two cases are added, both offline and credential-free against the isolated smoke home:

- `whoami` with no stored credential → exit 4, `AUTH_REQUIRED`.
- `--json whoami` with no stored credential → machine error document, exit 4.

No smoke case may make a network call, so login's success path is covered by the Phase 5 script
against a loopback server, not here.

---

## 7. Data Model Changes

N/A — this repository persists no database. The only persisted shapes are `ConfigDocument` and
`CredentialDocument`, and neither changes. No migration is required; `StateMigration` is called
by login exactly as it is today.

The one storage-adjacent behavior change is that `CredentialStore.write` becomes **reachable**
for the first time, since `PendingCredentialVerifier` previously blocked every login. The keyring
and fallback-file code paths have therefore never executed in a released build. §12 treats them
as new-code risk despite being old code.

---

## 8. API Changes

This repository implements no backend endpoints. One existing route becomes a CLI consumer.

### 8.1 POST /api/skills/auth/validate

**Change type:** Existing backend route (`backend/routes/skills.py:184`), new CLI consumer. No
server-side change is requested or required.

**Request:**

```
POST /api/skills/auth/validate
x-api-key: vb_live_...
Accept: application/json
(no body)
```

**Response 200:**

```json
{
  "success": "bool - true when the key resolved to a live principal",
  "session_token": "string - a live 30-day skills session; deliberately ignored by the CLI",
  "username": "string - the principal's user id (backend sets username = user_id)",
  "email": "string - also the user id, not an email; deliberately ignored by the CLI",
  "account_tier": "string - hardcoded \"free\" at backend/routes/skills.py:281"
}
```

**Error cases:**

| Status | Backend code | Condition | CLI failure |
|--------|--------------|-----------|-------------|
| 400 | `MISSING_API_KEY` | header absent or blank | `ApiRequestRejected` |
| 400 | `INVALID_KEY_FORMAT` | fails `is_valid_api_key_format` or hashing | `ApiRequestRejected` |
| 401 | `INVALID_API_KEY` | hash resolves to no principal | `ApiCredentialRejected` |
| 401 | `KEY_REVOKED` | principal status REVOKED | `ApiCredentialRejected` |
| 401 | `KEY_DISABLED` | principal status DISABLED | `ApiCredentialRejected` |
| 401 | `KEY_EXPIRED` | principal status EXPIRED | `ApiCredentialRejected` |
| 403 | `CORS_ORIGIN_REJECTED` | unreachable from a CLI (no `Origin` sent) | `ApiCredentialRejected` |
| 403 | `IP_BLOCKED` | caller IP on the block list | `ApiCredentialRejected` |
| 429 | `RATE_LIMIT_EXCEEDED` | >5/IP/15min or >100 global/15min | `ApiTemporarilyUnavailable` |
| 500 | `SKILLS_INTERNAL_ERROR` | handler or middleware exception | `ApiTemporarilyUnavailable` |

The `code` column documents what the backend sends; the CLI branches on **status only** (§5).

**Server-side side effect:** a 200 inserts one document into the skills sessions collection via
`create_skill_session`, expiring after `SESSION_TTL_DAYS = 30` under the `expires_at` TTL index.

### 8.2 GET /auth/whoami

**Change type:** Removed CLI consumer. The route never existed; `AuthEndpoints.whoami()` and the
`WhoAmI` model that named it are deleted.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/login-key-verification.md` | This document; first commit on the branch |
| CREATE | `src/vidbyte_cli/lib/api/README.md` | Transport boundary rules; every other `lib/*` has one |
| CREATE | `scripts/test_login_key_verification.py` | Phase 5 verification script |
| MODIFY | `src/vidbyte_cli/lib/api/client.py` | Implement `post_direct` + transport/decode/classify |
| MODIFY | `src/vidbyte_cli/lib/api/endpoints/auth.py` | Replace `whoami()` with `validate()` |
| MODIFY | `src/vidbyte_cli/types/api.py` | Delete `WhoAmI`, add `KeyIdentity` |
| MODIFY | `src/vidbyte_cli/lib/auth/verifier.py` | Delete `PendingCredentialVerifier`, add `ApiCredentialVerifier`, protocol returns `KeyIdentity` |
| MODIFY | `src/vidbyte_cli/lib/auth/__init__.py` | Export swap |
| MODIFY | `src/vidbyte_cli/lib/auth/README.md` | The "PR 4 seam" paragraph is now false |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Default `verifier_factory` to `ApiCredentialVerifier` |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Delete `CredentialVerificationUnavailable`; add 8 classes; reword `AuthenticationRequired.trace` |
| MODIFY | `src/vidbyte_cli/commands/auth/whoami.py` | Implement the command |
| MODIFY | `scripts/smoke.py` | `vidbyte_cli.cli` httpx boundary + two `whoami` cases |
| MODIFY | `README.md` | `whoami` is no longer unimplemented |
| UNCHANGED | `src/vidbyte_cli/commands/auth/login.py` | Already correct; zero lines change |

**Totals: 3 created, 11 modified, 0 deleted.**

Files deliberately **not** touched, per the field guide's "touch only the assigned files" rule:
`lib/api/client.py`'s three envelope methods, `lib/polling/`, `lib/operations/`,
`lib/harness/*`, `commands/harness/*`, `commands/setup/doctor.py`, `lib/errors/handler.py`
(no new foreign exception type reaches the boundary — every failure is already a `CliError`).

---

## 10. Testing Plan

The repository has no unit-test framework; the field guide's canonical gate is
`python scripts/run_ci.py`, and the design-doc workflow's gate is a standalone script. Both are
used. `scripts/test_login_key_verification.py` runs every case below.

**Test harness approach.** A `http.server.ThreadingHTTPServer` bound to `127.0.0.1:0` serves
scripted responses. This is possible because `ApiOrigin.parse` (`config/models.py:72-73`) permits
cleartext HTTP on loopback origins — so the tests exercise the **real** transport end to end with
no test-only parameter added to production code, and they also prove the loopback config path
works. `KeyringCredentialStore.__init__` already accepts an injected `backend`, so storage
assertions use an in-memory fake with a controllable `priority` rather than monkeypatching.

### Unit Tests

`ApiClient._url`

- `it('builds https://host + /path with no separator duplication')` — [Edge Case]
- `it('rejects an absolute http:// URL supplied as a path')` — [Hidden Assumption] — an endpoint
  group could hand it a full URL; without this the `x-api-key` header goes to a foreign host.
- `it('rejects a protocol-relative //evil.test/x path')` — [Hidden Assumption]
- `it('rejects a path that does not start with /')` — [Edge Case]
- `it('preserves a non-default port from the configured origin')` — [Silent Failure] — dropping
  the port would silently talk to :443 instead of the configured host.

`ApiClient._send`

- `it('sends the key in x-api-key and in no other header')` — [Silent Failure] — the server
  records every received header; the assertion is that the secret appears in exactly one.
- `it('sends no request body and no query string')` — [Silent Failure] — a key in a query string
  lands in access logs.
- `it('does not follow a 302 to another origin')` — [Hidden Failure] — the redirect target
  server asserts it received zero requests.
- `it('raises ApiUnreachable when the port is closed')` — [Hidden Assumption] — the assumption
  that the network works.
- `it('raises ApiUnreachable, not a credential failure, when the server never responds')` —
  [Hidden Failure] — server sleeps past a 1-second configured timeout. This is the single most
  important test in the file: conflating these two sends users to rotate a working key.

`ApiClient._decode`

- `it('returns the model for a well-formed 200')` — happy path
- `it('raises ApiProtocolError for an empty body')` — [Edge Case]
- `it('raises ApiProtocolError for a 204')` — [Edge Case]
- `it('raises ApiProtocolError for content-type text/html')` — [Hidden Assumption] — the captive
  portal / reverse-proxy error page case.
- `it('accepts application/json; charset=utf-8')` — [Edge Case] — parameterized media type.
- `it('accepts a body of exactly _MAX_RESPONSE_BYTES')` — [Edge Case]
- `it('raises ApiProtocolError for a body one byte over the bound')` — [Edge Case]
- `it('raises ApiProtocolError for malformed JSON')` — [Edge Case]
- `it('raises ApiProtocolError for a JSON array instead of an object')` — [Edge Case]
- `it('raises ApiProtocolError when username is missing')` — [Silent Failure] — otherwise
  `whoami` prints an empty identity and login stores the key anyway.
- `it('raises ApiProtocolError when username is an empty string')` — [Silent Failure]
- `it('ignores session_token and email rather than failing on them')` — [Hidden Assumption] —
  proves `extra="ignore"` is in force; a `forbid` default here would reject every real response.

`ApiClient._failure_for_status`

- `it('maps 401 to ApiCredentialRejected with exit 4')` — [Edge Case]
- `it('maps 403 to ApiCredentialRejected')` — [Edge Case]
- `it('maps 400 to ApiRequestRejected with exit 2')` — [Edge Case]
- `it('maps 404 to ApiRouteMissing')` — [Hidden Assumption] — the route is deployed. If the
  backend serving `config.api_url` predates the skills router, this is what fires, and it must
  not read as "your key is bad".
- `it('maps 429 to a retryable ApiTemporarilyUnavailable')` — [Edge Case]
- `it('surfaces the Retry-After value in the 429 hint')` — [Edge Case]
- `it('ignores a non-numeric Retry-After rather than crashing')` — [Hidden Failure]
- `it('maps 503 to a retryable ApiTemporarilyUnavailable')` — [Edge Case]
- `it('maps 418 to ApiOperationFailed')` — [Edge Case] — the default arm is exercised.
- `it('carries x-request-id into the failure when present')` — [Silent Failure] — an absent
  request id makes support correlation impossible.
- `it('ignores an x-request-id longer than 128 characters')` — [Edge Case]
- `it('never puts the response body into the failure message or description')` — [Silent
  Failure] — the server returns a body containing the literal key; the assertion is that no
  rendered field contains it.

`ApiCredentialVerifier`

- `it('returns KeyIdentity for a 200 with success true')` — happy path
- `it('raises ApiProtocolError for a 200 with success false')` — [Silent Failure] — the highest-
  value silent failure in the design: a 200 that denies success would otherwise store the key.

`WhoamiCommand`

- `it('raises AuthenticationRequired with no stored credential')` — [Hidden Assumption]
- `it('makes no network call when there is no stored credential')` — [Hidden Failure] — the test
  server asserts zero requests received.
- `it('prefers VIDBYTE_API_KEY over the keyring')` — [Silent Failure] — reporting the keyring
  identity while commands use the env key would be a wrong answer that looks right.
- `it('prints username and account_tier and never the key or session_token')` — [Silent Failure]
- `it('emits kind auth.whoami with schema_version 1 under --json')` — [Edge Case]

### Integration Tests

End-to-end through `LoginCommand.execute` against the loopback server, with a real
`CredentialStore` over an injected in-memory keyring backend and a temp `VidbytePaths`.

- `it('stores the key in the keyring only after a 200')` — the full happy path.
- `it('writes nothing to keyring or fallback file on 401')` — **the core requirement.**
  [Hidden Assumption]
- `it('writes nothing on a transport failure')` — [Hidden Assumption]
- `it('writes nothing on 500')` — fail-closed. [Hidden Assumption]
- `it('writes nothing on a 200 the decoder rejects')` — [Silent Failure] — the compound case
  where the network worked, the status was fine, and the payload was garbage.
- `it('sends exactly one request per login attempt')` — [Hidden Failure] — proves FR10: no
  retry, so the 5-per-15-minute budget is not silently consumed at 3× the rate. The server
  counts requests.
- `it('leaves an existing stored credential intact when a new login is rejected')` —
  [Silent Failure] — a failed re-login must not clear or corrupt the working key already there.
- `it('uses the same code path for login and whoami')` — asserts both routes hit the same
  server path, which is the literal FR11 requirement.

**Mocked vs real:** the HTTP server is real (a loopback socket, real httpx, real TLS-free
transport). The keyring backend is a fake, because a real one would prompt for an OS unlock in
CI. The filesystem is real, under a temporary directory.

**Silent failure paths between components:** the two that unit tests cannot reach are (a) a
verifier that succeeds while `CredentialStore.write` silently no-ops — covered by reading the
credential back after login rather than trusting the return value; and (b) a failure that
propagates as the wrong *kind*, which is why every negative case asserts the exact exit code, not
merely that an exception was raised.

**Hidden assumptions the integration surfaces:** that `ResolvedConfig.api_url` normalization
round-trips through `CredentialScope.account` consistently between the write and the read-back
(the non-default-port test covers the case where it would not).

### Manual / QA Test Cases

1. Given a valid `vb_live_` key, when `vidbyte-cli login --with-token` reads it from stdin, then
   the command exits 0 and `vidbyte-cli whoami` prints the same username. — happy path
2. Given a deliberately corrupted key (valid prefix, wrong body), when logging in, then the
   command exits 4 and `vidbyte-cli whoami` still reports the **previous** key's identity,
   proving nothing was overwritten. — [Silent Failure]
3. Given `VIDBYTE_API_URL=http://127.0.0.1:1` (a closed port), when logging in, then the error
   says the API could not be reached and does **not** mention an invalid key. — [Hidden Failure]
4. Given six `vidbyte-cli whoami` invocations inside 15 minutes from one IP, then the sixth
   returns the rate-limit failure with a `Retry-After` hint rather than an unexplained error. —
   [Edge Case] — this is the §13 constraint made visible.
5. Given a machine with no OS keyring and no `--allow-file-fallback`, when logging in with a
   **valid** key, then the key is verified, `NoApprovedCredentialStore` is raised, and nothing is
   written. — [Hidden Assumption] — verification succeeding does not imply storage succeeding.
6. Given `--json login`, when the key is rejected, then stderr carries exactly one
   `schema_version: 1, kind: "error"` document, stdout is empty, and neither stream contains the
   key. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `httpx` | `>=0.27,<1`, already declared in `pyproject.toml:15` | HTTP transport | None new. Imported lazily inside `_send` to protect startup time (NFR-1). |
| `pydantic` | `>=2.6,<3`, already declared | Response validation | None new. |
| `POST /api/skills/auth/validate` | `https://api.vidbyte.ai` | Key liveness check | **Rate limited to 5/IP/15min.** Writes a session document per call. Unverified against the deployed host — see §13. |
| `http.server` | stdlib | Phase 5 test server | Test-only; never imported by `src/`. |

No new dependency is added.

---

## 12. Rollout & Deployment

- **Feature flags:** none. A flag would mean shipping a build that still cannot log in, which is
  the state this change exists to end.
- **Breaking change:** yes, in the honest direction. Today every `login` fails with
  `CredentialVerificationUnavailable`; after this change a valid key succeeds and an invalid one
  fails with a different code. No user has a working stored credential to break, because
  `CredentialStore.write` has never been reachable in a released build — so there is no
  migration path to write.
- **New-code risk in old code:** for the same reason, the keyring write path, the restricted-file
  fallback, the consent prompt, and `StateMigration.migrate_if_needed()` on the login path have
  never executed in a shipped build. The Phase 5 integration tests exercise all of them, and QA
  case 5 covers the no-keyring branch specifically.
- **Deployment order:** none required. The backend route already exists in production and is
  unchanged.
- **Rollback:** revert the single commit that changes `lib/runtime/context.py:74`. That restores
  the failing-closed verifier without touching anything else, which is why the default binding is
  kept as a one-line change rather than being inlined. Full revert of the branch is also clean —
  nothing persists state that would outlive it.

---

## 13. Open Questions

- [ ] **Is `/api/skills/auth/validate` actually served at `https://api.vidbyte.ai`?** Verified in
      source (`backend/routes/skills.py:184`, registered via `skills_router` at `app.py:106`), not
      against the deployed host. One `curl -i -X POST https://api.vidbyte.ai/api/skills/auth/validate
      -H "x-api-key: vb_live_..."` closes it. If it 404s, `ApiRouteMissing` fires with wording
      that says exactly that, so the failure is legible rather than mysterious.
- [ ] **Is 5 validate calls per IP per 15 minutes tolerable for `whoami`?** This is the sharpest
      trade in the design. `whoami` is a command people run repeatedly, and agents are this
      CLI's heaviest callers. A shared CI egress IP exhausts the budget almost immediately. The
      change ships honoring the stated requirement ("'who am I?' uses that same check") and makes
      the 429 legible, but the durable fix is a read-only twin — see §14 Alternative 3.
- [ ] **Should the CLI accept `vb_test_` keys?** The backend's `is_valid_api_key_format` accepts
      `vb_live_` **and** `vb_test_` (`backend/lib/hash/api_key_utils.py:43-53`), while
      `Credentials.is_live_format` accepts only `vb_live_`. A test key is therefore rejected
      locally before the backend ever sees it. That narrowing landed deliberately in PR #14 and
      is out of scope here, but it will surprise someone.
- [ ] **Should `account_tier` be surfaced at all?** It is hardcoded to `"free"` at
      `backend/routes/skills.py:281`, so it currently conveys nothing. It is included because it
      is part of the documented response and will become meaningful; the alternative is adding it
      later as a breaking output change.
- [ ] **Does the deployed backend set `x-request-id` as a response header?** Skills errors carry
      `request_id` in the **body**. The design reads the header only, so `request_id` may be
      absent in practice. Reading it from the body would mean parsing an error shape that is not
      consistent across the backend (§5), so this is accepted for now.

---

## 14. Alternatives Considered

### Alternative 1: Verify via `GET /auth/whoami` (the `feat/research-api-wiring` implementation)

- **What:** Reuse the finished `ApiCredentialVerifier` already written on the side branch.
- **Why rejected:** The route does not exist. `backend/app.py:89-110` registers no `/auth/*`
  router. Because `/auth/whoami` is also absent from `_API_KEY_ONLY_ROUTE_PERMISSIONS`, the
  request would not even reach a 404 — `AuthHeaderMiddleware` falls through to the JWT branch and
  returns a 401 about bearer tokens, so the CLI would report "invalid key" for a missing route.
  A misleading failure is worse than a clean one.

### Alternative 2: Verify via a cheap authenticated resource read (`GET /project/list?limit=1`)

- **What:** Prove the key by doing something with it.
- **Why rejected:** It proves the wrong thing. `_API_KEY_ONLY_ROUTE_PERMISSIONS`
  (`backend/middleware/api_platform.py:40-57`) grants read and write separately —
  `("/project/list", "projects:read")` versus `("/project/create", "projects:write")`. A key
  scoped only to write is perfectly valid and fully paid up, and this check would 403 it, making
  login **stricter than the product**. The mirror case is just as bad: a key holding
  `projects:read` but not the scope its owner actually needs would pass login, get written to the
  keyring, and 403 on the first real command. Login must answer "is this key alive?"; capability
  belongs at the point of use, where a 403 can name the missing scope.

### Alternative 3: Add a read-only `GET /api/skills/auth/identity` to the backend

- **What:** A ~25-line twin of `validate_auth` running lines 199–273 of `backend/routes/skills.py`
  and returning `{user_id, key_prefix, status}` with no `create_skill_session` call and no
  session token.
- **Why rejected *for this change*:** the stated constraint is to verify against something that
  exists today, and this repository implements no backend routes.
- **The condition that flips it:** any backend work landing in the same window. It removes the
  per-call Mongo write, removes the stray live `session_token` from the response entirely, and —
  most importantly — would not carry the 5-per-15-minute auth-attempt budget, which is what makes
  `whoami` awkward. This is the right long-term route and should be the first follow-up. Given
  `/harness/*` has to be built server-side anyway, folding it in is cheap.

### Alternative 4: Branch on the backend's `code` field instead of the HTTP status

- **What:** Map `KEY_REVOKED`, `KEY_DISABLED`, `KEY_EXPIRED`, and `INVALID_API_KEY` to four
  distinct CLI failures instead of collapsing them into `ApiCredentialRejected`.
- **Why rejected:** the backend serves three incompatible error shapes —
  `{error, code, message, request_id}` from skills routes,
  `{error, title, subtitle}` from `AuthHeaderMiddleware`, and `{code, title, detail}` from
  `PublicApiResponseFactory`. `code` is therefore a skills-route detail, not a platform contract,
  and teaching the generic `ApiClient` one of the three spellings would be wrong as soon as
  `/harness/*` lands. The information loss is small: all four mean "this key will not work, get a
  new one," and `ApiCredentialRejected.description` enumerates them.
- **The condition that flips it:** the Gate API refactor unifying the backend on one error
  envelope. At that point `code`-first classification with a status fallback is correct, and it
  is exactly what §6.4 step 4 of the program design doc already specifies.

### Alternative 5: Implement the full PR 4 HTTP platform now

- **What:** `RetryPolicy`, `ResponseShape`, `IdempotencyKeyFactory`, `OperationJournal`, `Poller`,
  and a generic `ApiClient.request(...)`, per §6.4 of the program design doc.
- **Why rejected:** four of the five routes that platform exists to serve do not exist on the
  backend. Building retry semantics, idempotency records, and a three-member `ResponseShape` enum
  against one real endpoint means designing against an imagined API, and the resulting code would
  never have executed. `post_direct` is the whole of what this feature needs; PR 4 folds it into
  `request(..., response_shape=ResponseShape.DIRECT)` when there is something to generalize over.

### Alternative 6: Import `httpx` at `client.py` module scope

- **What:** The conventional placement.
- **Why rejected:** measured cost. `vidbyte-cli --version` runs in 0.226 s today and a cold
  `import httpx` costs 0.138 s; `commands/__init__.py` imports every command eagerly, so
  `login.py → runtime.context → lib.auth → verifier → api.client` would put httpx on the
  `--help` path. A ~60% startup regression on the two commands agents call most is not worth
  conventional import placement. `scripts/smoke.py` enforces the boundary so it cannot regress
  silently.

---

## Summary

**Files: 3 created, 11 modified, 0 deleted.** `commands/auth/login.py` — the file this feature is
named after — does not change at all.

**Key risks:**

1. `/api/skills/auth/validate` is verified in source but not against the deployed host. If it is
   not there, `ApiRouteMissing` says so plainly.
2. The 5-per-IP-per-15-minute rate limit makes `whoami` genuinely awkward for repeated or CI use.
   Shipped as specified, with a legible 429 and a named follow-up (§14 Alternative 3).
3. The keyring write path has never executed in a released build, because the pending verifier
   blocked it. Old code, new risk.

**Open questions needing your call:** whether to accept the `whoami` rate-limit trade now and fix
it with a backend twin later (recommended), and whether `account_tier` should be surfaced while
it is still hardcoded to `"free"`.

**Requesting explicit approval before Phase 3 (worktree) and Phase 4 (implementation).**
