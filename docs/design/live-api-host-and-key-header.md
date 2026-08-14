# Design Doc: Live API Host and API-Key Header

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-14
**Last Updated:** 2026-08-14

---

## 1. Overview

The CLI's factory-default API host is `https://api.vidbyte.ai`, which is not the public
Vidbyte API. The live service is `https://vidbyte-backend.onrender.com`, and its gatekeeper
authenticates a request by reading the `x-api-key` header and accepting only keys carrying
the `vb_live_` prefix. This change repoints the factory default at the real host, makes
`ApiClient` receive its resolved settings and credential through the constructor instead of
re-reading the environment, gives it the single place where the `x-api-key` header is built,
and rejects a non-live key at the two boundaries where a human or a CI configuration can
still fix it — so a key the gatekeeper would silently ignore never reaches storage and never
presents as a mysterious "not logged in".

---

## 2. Goals & Non-Goals

### Goals

- Change the single factory-default API host to `https://vidbyte-backend.onrender.com`.
- Collapse the twice-declared `DEFAULT_API_URL` constant to one declaration in `lib/config`.
- Make `ApiClient` take `ResolvedConfig` and `Credentials` through its constructor and stop
  reading `os.environ`, satisfying program requirement 24.
- Give `ApiClient` the one method that builds the authentication header, using `x-api-key`.
- Route `HarnessContext`'s credential lookup through `CredentialResolver` so an exported
  `VIDBYTE_API_KEY` outranks a stale stored key, as `lib/auth/resolver.py` documents.
- Reject a non-`vb_live_` key at login input and at the `VIDBYTE_API_KEY` environment branch,
  with typed failures that say "wrong format" rather than letting it surface later as 401.
- Keep loopback HTTP development hosts working and non-loopback HTTP hosts refused.
- Update `README.md` and `.env.example`, which both currently document the dead host.

### Non-Goals

- **HTTP transport.** `ApiClient.get`/`get_list`/`post` continue to raise
  `NotImplementedFeature`. Transport, retry, idempotency, envelope decoding, and the API
  error taxonomy are PR 4 of the seven-PR program
  (`docs/design/python-cli-research-harness-program.md` §6.4). Implementing them here would
  violate the field guide's "touch only the files the design doc assigns to this PR" rule and
  duplicate a designed PR.
- **An HTTP-backed `CredentialVerifier`.** It depends on transport, and separately on a
  backend verification route that does not exist (see §12).
- **Re-validating already-stored credentials against the `vb_live_` prefix.** Nothing can be
  stored today, because `PendingCredentialVerifier` refuses every login. See §13.
- **Re-scoping existing keyring entries after the host change.** Same reason.
- **A config-document migration** for a profile that pinned `api_url` to the old host.
- Any change to the `vidbyte` backend repository.
- New test files. Existing gates (`python scripts/run_ci.py`) must stay green.

---

## 3. Background & Context

`vidbyte-cli` is a Python 3.11+ Click/Pydantic/HTTPX CLI at version `0.1.0`, built as a
seven-PR program. The configuration, credential, output, and error platforms have landed;
the networking platform has not. The result is a repo where the *shape* of every API call is
declared but no call is made.

Three defects sit in that gap.

**The host is wrong.** `DEFAULT_API_URL` is `https://api.vidbyte.ai` in two separate files —
`lib/config/models.py:22` and `lib/api/client.py:17`. Neither is the public API. The
canonical host is `https://vidbyte-backend.onrender.com`, recorded in the main repo's
`skills/api/central-vidbyte-api.md` and used as `API_BASE_URL` by the docs registry. Because
the constant is declared twice, changing one leaves the other pointing at the dead host.

**`ApiClient` bypasses the resolvers.** The repo has a five-layer `ConfigResolver` with
provenance and a separate `CredentialResolver` with its own precedence, and then:

```python
self.base_url = base_url or os.environ.get("VIDBYTE_API_URL") or DEFAULT_API_URL
self._api_key = api_key or os.environ.get("VIDBYTE_API_KEY")
```

A stale exported `VIDBYTE_API_URL` outranks the profile a user deliberately wrote with
`config set api_url`, and — more seriously — the value that gets dialed never passes through
`ApiOrigin.parse`, so the loopback/HTTPS guard in `lib/config/models.py:72-73` is bypassed on
the only code path that makes requests. Program
requirement 24 already forbids this: "`ApiClient` MUST receive resolved settings and
credentials through its constructor; it MUST NOT read environment variables itself."

`HarnessContext.require_api_key` has the mirror-image defect on the secret side: it calls
`CredentialStore.read` directly rather than `CredentialResolver.resolve`, so an exported
`VIDBYTE_API_KEY` loses to a stored keyring key — the exact inversion `lib/auth/resolver.py`'s
docstring says must not happen ("a CI job exporting `VIDBYTE_API_KEY` must win over whatever
a developer once stored on the same machine").

**A non-live key is invisible rather than rejected.** The gatekeeper is
`backend/middleware/api_platform.py:80-102` in the `vidbyte` repo:

```python
header_value = str(x_api_key or "").strip()
if header_value:
    if header_value.startswith(API_KEY_FORMAT_PREFIX):  # "vb_live_"
        return header_value
    return None
```

A `vb_test_` key yields no candidate at all, so API-key auth never runs and the request falls
through to session authentication and fails as unauthenticated. The CLI's own
`Credentials.validate_api_key` only checks `1 <= len <= 4096`, so it would accept such a key,
store it, and fail every later command with no usable explanation.

The header choice follows from the same function. Both `x-api-key` and `Authorization: Bearer`
are accepted for a `vb_live_` key and produce an identical principal — `candidate_source` is
recorded into `ApiKeyAuthRequestDto` and never read for any behavioural decision. `x-api-key`
is checked first, is the declared canonical name (`API_KEY_HEADER_NAME` at
`api_platform.py:5`), and is what the public docs show. The decisive detail is the
`return None` above: a request carrying *both* headers with a non-live `x-api-key` is dropped
without falling through to `Authorization`. So the client sends exactly one header, and it is
`x-api-key`.

---

## 4. Requirements

### Functional Requirements

1. `DEFAULT_API_URL` MUST be declared exactly once, in `lib/config/models.py`, with the value
   `https://vidbyte-backend.onrender.com`.
2. `lib/api/client.py` MUST NOT declare its own `DEFAULT_API_URL`.
3. A fresh install with no configuration file, no profile, and no `VIDBYTE_*` variables MUST
   resolve `api_url` to `https://vidbyte-backend.onrender.com`.
4. `ApiClient.__init__` MUST accept a `ResolvedConfig` and a `Credentials` and MUST NOT read
   any environment variable.
5. `ApiClient` MUST expose exactly one method that builds request authentication headers, and
   it MUST emit the key under the header name `x-api-key`.
6. `ApiClient` MUST NOT emit an `Authorization` header for API-key authentication.
7. `ApiClient` MUST carry `request_timeout_seconds` from the resolved configuration so the
   transport PR has it without another signature change.
8. `HarnessContext` MUST resolve its credential through `CredentialResolver`, so precedence is
   environment → OS keyring → restricted file.
9. `HarnessContext` MUST hold the invocation's `ResolvedConfig` and pass it to `ApiClient`,
   rather than an optional raw `base_url` string.
10. Login input MUST reject a token that does not begin with `vb_live_`, before verification
    and before any storage attempt, with a typed usage failure.
11. `CredentialResolver` MUST reject a `VIDBYTE_API_KEY` that does not begin with `vb_live_`
    with a typed authentication failure, rather than falling through to stored credentials.
12. Both new failures MUST be `CliError` subclasses in `lib/errors/failures.py` carrying
    `message`, `description`, `trace`, and `hint`, and MUST NOT echo the rejected value.
13. Non-loopback `http://` API URLs MUST remain refused; `http://localhost`, `http://127.0.0.1`,
    and `http://[::1]` MUST remain accepted, and that guard MUST now also cover the value
    `ApiClient` dials.
14. `README.md` and `.env.example` MUST document `https://vidbyte-backend.onrender.com`.
15. Commands that have no transport MUST keep failing with `NotImplementedFeature`; this
    change MUST NOT make an unimplemented command appear to work.

### Non-Functional Requirements

- **Performance:** No new import at package-import time. `scripts/smoke.py`'s import-boundary
  case asserts neither `click` nor `httpx` is loaded by `import vidbyte_cli`; that must hold.
- **Scalability:** N/A — this is a client-side constant, constructor, and header change with
  no data volume dimension.
- **Security:** The key stays a `SecretStr` until the single point where the header is built.
  No failure message, `description`, `trace`, or log line may quote a key, and the `vb_live_`
  rejections must report only that the format is wrong. Non-loopback cleartext HTTP stays
  refused, and that guard now covers the dialed value rather than only the stored one.
- **Observability:** `vidbyte-cli doctor` already prints the resolved `API URL` and the
  credential's source, which is how the host change is verified offline. No new output.
- **Reliability:** Every failure path is a typed `CliError` with a stable code and exit status.
  A rejected key leaves no local state changed and makes no network call.

---

## 5. High-Level Design

The change is a constant, a constructor, a header, and a guard. No new module, no new layer,
no new dependency.

**The constant.** `lib/config/models.py` keeps the sole `DEFAULT_API_URL` and takes the new
value. `lib/api/client.py` deletes its duplicate. Everything downstream — `ProfileConfig`'s
field default, `ConfigResolver`'s fallback, `CredentialScope`'s account name, the legacy
migration's scope check — already reads that one constant, so the host change propagates
without further edits.

**The constructor.** `ApiClient` stops being a thing that looks up its own configuration and
becomes a thing that is handed one. It takes `ResolvedConfig` (already `ApiOrigin`-normalized
by the `NormalizedApiUrl` annotation, so validation is structural rather than a call someone
can forget) and `Credentials`. The `os` import goes away. This satisfies program requirement
24 and, as a side effect, closes the guard bypass: there is no longer a path where an
unvalidated string reaches `base_url`.

**The header.** One method, `auth_headers`, returns `{"x-api-key": <key>}`. It is the only
place the secret is unwrapped for transmission, and PR 4's `request` method will merge it with
user-agent, request-id, and idempotency headers.

**The guard.** `Credentials` grows an `is_live_format` classmethod naming the `vb_live_`
prefix. Two call sites use it: `CredentialInput.read`, which is where a person types or pipes
a key, and `CredentialResolver.resolve`'s environment branch, which is where CI supplies one.
Each raises its own typed failure, mirroring how `InvalidApiKeyInput` and
`InvalidEnvironmentApiKey` already split the same conceptual failure across the same two
channels.

`HarnessContext` is the seam that ties these together: it is the only place `ApiClient` is
constructed, and it currently reaches for the credential store directly. It gains the
invocation's `ResolvedConfig` and a `CredentialResolver` in place of `base_url`, `profile`,
and `CredentialStore`.

```
ConfigResolver ──> ResolvedConfig (api_url: NormalizedApiUrl, timeout) ──┐
                                                                        ├──> ApiClient
CredentialResolver ──> ResolvedCredential ──> Credentials ──────────────-┘        │
   env → keyring → file          │                                               │
                                 └── vb_live_ guard (env branch)         auth_headers()
                                                                          {"x-api-key": …}
CredentialInput ──> vb_live_ guard ──> CredentialVerifier ──> CredentialStore.write
```

Both resolvers are constructed once per invocation by `ApplicationContext` and reused, so
`_build_harness_context` simply forwards what it already holds.

---

## 6. Detailed Design

### 6.1 Default API host constant

**File(s):** `src/vidbyte_cli/lib/config/models.py`
**Type:** Modified

#### What it does

Holds the single factory-default API origin every other module reads.

#### Interface / API

```python
DEFAULT_API_URL = "https://vidbyte-backend.onrender.com"
```

#### Logic / Algorithm

1. Change the value on line 22. Nothing else in the file changes.

#### Edge Cases & Error Handling

- The new value must survive `ApiOrigin.parse`: it is `https`, has a hostname, no userinfo,
  no path, no query, no fragment, and no explicit port. It normalizes to itself, so
  `ProfileConfig`'s `NormalizedApiUrl` default validates unchanged.
- A user whose stored profile pins the old host keeps it; the stored profile outranks the
  built-in default and there is no migration (§11).

---

### 6.2 `ApiClient` constructor and authentication header

**File(s):** `src/vidbyte_cli/lib/api/client.py`
**Type:** Modified

#### What it does

Owns the base URL, the request timeout, and the one place the API key becomes a header. The
request methods stay unimplemented until PR 4.

#### Interface / API

```python
API_KEY_HEADER_NAME = "x-api-key"


class ApiClient:
    def __init__(self, config: ResolvedConfig, credentials: Credentials) -> None: ...
    def auth_headers(self) -> dict[str, str]: ...
    def get(self, path: str, model: type[TModel]) -> TModel: ...
    def get_list(self, path: str, model: type[TModel]) -> list[TModel]: ...
    def post(self, path: str, body: BaseModel, model: type[TModel]) -> TModel: ...
```

#### Logic / Algorithm

1. Delete the module-level `DEFAULT_API_URL` and the `import os`.
2. Add `API_KEY_HEADER_NAME = "x-api-key"` with a comment naming why this header and not
   `Authorization`.
3. `__init__` assigns `self.base_url = config.api_url`,
   `self.timeout_seconds = config.request_timeout_seconds`, and holds `credentials` privately.
4. `auth_headers` returns a fresh single-entry dict built from `credentials.secret_value()`.
5. The three request methods keep raising `NotImplementedFeature("api client requests")`.

#### Edge Cases & Error Handling

- `config.api_url` is typed `NormalizedApiUrl`, so a non-origin or non-loopback cleartext URL
  cannot reach the constructor — the failure happens earlier, in `ConfigResolver`, as
  `InvalidConfigOverride`.
- `auth_headers` returns a new dict per call so a caller mutating it (adding a request ID, an
  idempotency key) cannot corrupt the client's state.
- Only `x-api-key` is emitted. Emitting `Authorization` alongside it would be inert at best
  and, given the gatekeeper's early `return None` on a non-live `x-api-key`, actively
  misleading at worst.
- Neither the key nor the header dict is logged, and no `__repr__` is added — `Credentials`
  holds a `SecretStr`, and the unwrapped value exists only inside `auth_headers`' return.

---

### 6.3 Live-format check on `Credentials`

**File(s):** `src/vidbyte_cli/lib/auth/credentials.py`
**Type:** Modified

#### What it does

Names the prefix the backend gatekeeper requires, and answers whether a candidate token has
it, so the two input boundaries share one definition.

#### Interface / API

```python
LIVE_API_KEY_PREFIX = "vb_live_"


class Credentials(BaseModel):
    @classmethod
    def is_live_format(cls, value: str) -> bool: ...
```

#### Logic / Algorithm

1. Add the module constant next to the existing `_MAX_KEY_CHARACTERS` bound.
2. Add `is_live_format` as a classmethod on `Credentials`, returning `value.startswith(...)`.

#### Edge Cases & Error Handling

- The check is deliberately *not* added to the `validate_api_key` field validator. That
  validator also runs when reading the keyring and the restricted file, so making the prefix a
  type invariant would turn "clear my old bad key" into `StoredCredentialUnreadable` and make
  `logout` unable to remove exactly the credential a user most needs removed.
- The method goes on `Credentials` rather than into a free function because the field guide
  bars module-level helpers beside a class; `Credentials` has real state (`api_key`), which is
  the same justification `ProfileConfig.default_map` and `ApiOrigin.normalize` rest on.
- Whitespace is not stripped here — both call sites strip before calling.

---

### 6.4 Login input rejects a non-live key

**File(s):** `src/vidbyte_cli/lib/auth/input.py`
**Type:** Modified

#### What it does

Adds the format check to the boundary where a person types or pipes a key, so the rejection
happens while a human is present to fix it.

#### Logic / Algorithm

1. After the existing empty/oversize check in `read`, call `Credentials.is_live_format(token)`.
2. If it returns `False`, raise `ApiKeyNotLiveFormat`.
3. Otherwise construct `Credentials.from_value(token)` as before.

#### Edge Cases & Error Handling

- Ordering matters: the length bound runs first, so an accidentally redirected large file is
  still rejected as oversized rather than being prefix-tested in full.
- The rejected value is never echoed — it may be a real secret that was merely mistyped.
- This runs before `CredentialVerifier.verify` and therefore before any storage attempt, so a
  rejected key touches no keyring, no file, and no network.

---

### 6.5 Environment key rejects a non-live value

**File(s):** `src/vidbyte_cli/lib/auth/resolver.py`
**Type:** Modified

#### What it does

Applies the same format rule to `VIDBYTE_API_KEY`, which is the channel CI uses.

#### Logic / Algorithm

1. In `resolve`'s environment branch, after the existing empty/oversize check, call
   `Credentials.is_live_format(token)`.
2. If it returns `False`, raise `EnvironmentApiKeyNotLive`.

#### Edge Cases & Error Handling

- This is a raise, not a fall-through, for the reason already documented on the line above it:
  the variable is set, so it outranks the stores, and falling through would silently
  authenticate as whoever is stored locally.
- Consistent with `InvalidEnvironmentApiKey`, this is an authentication-class failure
  (exit 4), not a usage failure — the caller's command line was fine, their environment is not.

---

### 6.6 New typed failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Supplies the reviewable prose for the two rejections, following the one-class-per-failure rule.

#### Interface / API

```python
class ApiKeyNotLiveFormat(CliError):
    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE


class EnvironmentApiKeyNotLive(CliError):
    code = CliErrorCode.AUTH_REQUIRED
    exit_status = ExitCode.AUTHENTICATION
```

#### Logic / Algorithm

1. Add `ApiKeyNotLiveFormat` beside `InvalidApiKeyInput`, whose channel it shares.
2. Add `EnvironmentApiKeyNotLive` beside `InvalidEnvironmentApiKey`, likewise.
3. Each carries a 3–4 sentence `description` covering what was and was not done and whether
   retrying helps, a semantic `trace` of the path before the raise, and a `hint`.

#### Edge Cases & Error Handling

- `file_path` is derived by `CliError._origin_file()` and is never hand-written.
- No `cause` is attached: there is no underlying exception, and `cause` is the channel for
  values that must never be serialized.
- The `description` explains *why* a non-live key is worse than an invalid one — the server
  drops it without a candidate, so it presents as "not logged in" rather than as a bad key.

---

### 6.7 `HarnessContext` resolves credentials and carries resolved config

**File(s):** `src/vidbyte_cli/lib/harness/context.py`
**Type:** Modified

#### What it does

Injects the invocation's resolved settings and the credential *resolver* into the one place
`ApiClient` is constructed.

#### Interface / API

```python
@dataclass
class HarnessContext:
    credentials: CredentialResolver
    repo: RepoInspector
    logger: Logger
    render: RunRenderer
    config: ResolvedConfig
    paths: VidbytePaths | None = None

    def require_credentials(self) -> Credentials: ...
    def harness_endpoints(self) -> HarnessEndpoints: ...
    def manifest_cache_dir(self) -> str: ...

    @staticmethod
    def default(
        output: OutputManager,
        *,
        credentials: CredentialResolver,
        config: ResolvedConfig,
        paths: VidbytePaths | None = None,
    ) -> HarnessContext: ...
```

#### Logic / Algorithm

1. Replace the `credentials: CredentialStore` field with `credentials: CredentialResolver`.
2. Replace `base_url: str | None` and `profile: str` with `config: ResolvedConfig`.
3. Rename `require_api_key` to `require_credentials`, returning `Credentials` rather than a
   raw `str`, and resolve through `CredentialResolver.resolve(config.profile, config.api_url)`.
4. `harness_endpoints` constructs `ApiClient(self.config, self.require_credentials())`.
5. `default` takes `credentials` and `config` as required keyword arguments — it can no longer
   build a resolver itself, because a resolver needs an injected environment mapping and this
   module must not read `os.environ`.
6. Update the module docstring: profile and host now travel inside `ResolvedConfig`, and the
   scoping rationale it states is unchanged.

#### Edge Cases & Error Handling

- `resolve` raising `InvalidEnvironmentApiKey` or the new `EnvironmentApiKeyNotLive` now
  surfaces on harness commands too, which is correct: those were previously masked by the
  direct store read.
- No stored credential still raises `AuthenticationRequired`, unchanged.
- `AuthenticationRequired`'s `trace` names `HarnessContext.require_api_key`; it is updated to
  `require_credentials` and to say the resolver was consulted, so the trace stays true.
- No consumer outside this file reads `.base_url` or `.profile` (verified by grep across
  `src/`), so the field replacement has no further ripple.

---

### 6.8 `ApplicationContext` wiring

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

#### What it does

Forwards the resolver and resolved config it already owns into the harness context.

#### Logic / Algorithm

1. `_build_harness_context` passes `credentials=self.credential_resolver()` and
   `config=self.resolved_config()` instead of `credentials=self.credential_store()`,
   `base_url=...`, and `profile=...`.
2. `paths` is still forwarded.

#### Edge Cases & Error Handling

- `resolved_config()` already resolves on demand when Click short-circuits the root callback,
  so the harness context cannot be built with unresolved settings.
- `configure` still refuses an options change after the harness context exists, so the config
  captured here cannot silently disagree with the active output policy.
- Construction stays lazy: `_build_harness_context` runs only via `harness_context()`, so
  `--help` and `--version` still perform no credential resolution.

---

### 6.9 Documentation

**File(s):** `README.md`, `.env.example`
**Type:** Modified

#### What it does

Stops the CLI's own documentation from naming a host that is not the API.

#### Logic / Algorithm

1. `README.md` line 63: change the documented default to
   `https://vidbyte-backend.onrender.com`.
2. `.env.example` lines 1–2: same, in the comment and the value.

#### Edge Cases & Error Handling

- `.env.example` is illustrative only; nothing in the CLI loads a `.env` file.

---

### 6.10 `doctor` reports whether a stored key is live-format

**File(s):** `src/vidbyte_cli/commands/setup/doctor.py`
**Type:** Modified

*Added during Phase 5 refinement — see §14.*

#### What it does

Closes the last route to the symptom this change exists to remove. The §6.4/§6.5 guards cover
the login prompt and `VIDBYTE_API_KEY`, but a credential file written by hand crosses neither,
so `doctor` would report `present` for a key the backend silently ignores.

#### Logic / Algorithm

1. After resolving the credential, compute `Credentials.is_live_format(...)` on it, or `None`
   when no credential resolved.
2. Add `credential_live_format` to the machine document.
3. When it is `False`, append `- not a live key, the backend will ignore it` to the human
   credential line.

#### Edge Cases & Error Handling

- The value is never echoed; only the boolean is reported. Verified by asserting the secret
  does not appear in `--json doctor` output.
- `None` rather than `False` when no credential exists, so "absent" and "present but wrong"
  stay distinguishable to a machine caller.
- `doctor` stays read-only: it reports the condition and repairs nothing.

---

## 7. Data Model Changes

N/A — no database, collection, or persisted schema changes. `ConfigDocument` and
`CredentialDocument` both stay at `schema_version: 1` with identical fields; only the
*default value* of `ProfileConfig.api_url` changes, which is not a schema change and does not
affect a document already on disk.

---

## 8. API Changes

N/A — this repository defines no server endpoints. It consumes the `vidbyte` backend, and
that contract is unchanged: this change makes the CLI conform to the existing gatekeeper
(`x-api-key`, `vb_live_`) rather than altering it.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/live-api-host-and-key-header.md` | This design doc |
| MODIFY | `src/vidbyte_cli/lib/config/models.py` | Sole `DEFAULT_API_URL` takes the live host |
| MODIFY | `src/vidbyte_cli/lib/api/client.py` | Drop duplicate constant and `os` reads; take `ResolvedConfig`/`Credentials`; add `auth_headers` |
| MODIFY | `src/vidbyte_cli/lib/auth/credentials.py` | Add `LIVE_API_KEY_PREFIX` and `Credentials.is_live_format` |
| MODIFY | `src/vidbyte_cli/lib/auth/input.py` | Reject a non-live key at login input |
| MODIFY | `src/vidbyte_cli/lib/auth/resolver.py` | Reject a non-live `VIDBYTE_API_KEY` |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add `ApiKeyNotLiveFormat`, `EnvironmentApiKeyNotLive`; retrace `AuthenticationRequired` |
| MODIFY | `src/vidbyte_cli/lib/harness/context.py` | Hold `ResolvedConfig`, resolve via `CredentialResolver`, construct `ApiClient` |
| MODIFY | `src/vidbyte_cli/lib/harness/base.py` | Follow the `require_api_key` → `require_credentials` rename |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Forward resolver and resolved config |
| MODIFY | `src/vidbyte_cli/commands/setup/doctor.py` | Report `credential_live_format` (§6.10, refinement) |
| MODIFY | `src/vidbyte_cli/lib/auth/keyring_store.py` | Scope comment named the dead host as its example |
| MODIFY | `src/vidbyte_cli/lib/auth/README.md` | Document the live-format boundary |
| MODIFY | `docs/design/python-cli-research-harness-program.md` | Two `api.vidbyte.ai` references that would reimplement the dead host |
| MODIFY | `docs/design/harness-runtime-and-cli-scaffold.md` | Lifecycle description named `require_api_key` |
| MODIFY | `README.md` | Documented default host |
| MODIFY | `.env.example` | Documented default host and the live-key requirement |

17 files: 1 created, 16 modified, 0 deleted.

`base.py`, `keyring_store.py`, `doctor.py`, and the two sibling design docs were not in the
pre-implementation manifest; each was added for a named reason recorded above and in §14,
rather than as opportunistic editing.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte backend | `https://vidbyte-backend.onrender.com` | The live public API this CLI targets | Host is a Render deployment, not a custom domain; if it moves behind `api.vidbyte.ai` later, this constant plus the docs registry and SDK constants must change together |
| Backend gatekeeper contract | `x-api-key` header, `vb_live_` prefix | How a request authenticates | Contract read from `backend/middleware/api_platform.py`; a change to `API_KEY_FORMAT_PREFIX` or `API_KEY_HEADER_NAME` silently breaks this client |
| `pydantic` | `>=2.6,<3` | `ResolvedConfig`, `Credentials`, `SecretStr` | Already a dependency; unchanged |
| `httpx` | `>=0.27,<1` | Transport | Already declared; still unused by this change |

No dependency is added, removed, or version-changed.

---

## 11. Rollout & Deployment

- **Feature flags:** None. A default host behind a flag would mean shipping a CLI that talks
  to the wrong service unless a user opts in, which is the defect being fixed.
- **Breaking change:** Technically yes, in two ways, both assessed as inert at `0.1.0`:
  1. `ApiClient.__init__` and `HarnessContext`'s fields change shape. Both are internal;
     neither is exported from `vidbyte_cli/__init__.py`, and `ApiClient` has exactly one
     construction site in the repo.
  2. Credentials are keyed by host — `CredentialScope.account` is `f"{profile}@{host}"` — so a
     key stored under `default@api.vidbyte.ai` becomes unreachable once the default moves. No
     migration is written because no key can exist: `PendingCredentialVerifier` refuses every
     login, so `CredentialStore.write` is unreachable in every released build. If that
     assumption is wrong (§12), the recovery is one `vidbyte-cli login`, and the stale keyring
     entry is inert rather than dangerous.
- **Deployment order:** Single repository, single PR, no coordination with the backend. The
  backend already enforces `x-api-key`/`vb_live_`; this change conforms to it.
- **Rollback:** Revert the PR. No persisted state is written, migrated, or deleted by this
  change, so a revert restores the prior behaviour exactly.

---

## 12. Open Questions

- [ ] Is `https://vidbyte-backend.onrender.com` intended to be the durable public host, or a
      staging address ahead of `api.vidbyte.ai` going live? **Assumed durable** — confirmed by
      the user in this request, and consistent with the main repo's
      `skills/api/central-vidbyte-api.md` and docs registry. If it is temporary, this constant
      plus the docs registry and SDK constants must move together.
- [ ] **There is no backend route this CLI can authenticate against yet.** The gatekeeper's
      API-key surface (`_API_KEY_ONLY_ROUTE_PERMISSIONS` in `backend/middleware/api_platform.py`)
      contains only quickhits, roadmaps, quizzes, exams, projects, and `/agent/topup`. Neither
      `/auth/whoami` nor any `/harness/*` path is on it, and `is_api_key_route` returns `False`
      for anything else, which produces a 403 *before* the key is validated. So even with
      transport implemented, `login` and every harness command would fail against the live
      host. This is a backend gap, not a client one, and it bounds what "talks to the real
      service" can mean until those routes are mounted.
- [ ] Has any released build ever stored a credential? Assumed no, because
      `PendingCredentialVerifier` blocks the only write path. This is what makes the keyring
      re-scoping non-issue (§11).
- [ ] Should `vb_test_` keys ever be usable? The backend's `API_KEY_FORMAT_PREFIX` is
      `vb_live_` only, though `backend/orchestrators/api/constants.py` also defines a
      `TEST_PREFIX`. Assumed no for the CLI until the backend accepts one.

---

## 13. Alternatives Considered

### Alternative 1: Implement the HTTP transport in this PR

- **What:** Add httpx to `ApiClient.get`/`post`, envelope decoding, and an HTTP-backed
  `CredentialVerifier`, so `login` genuinely reaches the live host.
- **Why rejected:** That is PR 4 of the seven-PR program (§6.4 of
  `docs/design/python-cli-research-harness-program.md`), which also owns retry policy,
  idempotency journalling, polling, response-shape selection, and a whole API error family
  that does not exist in `lib/errors/failures.py` yet. The field guide's standing rule is to
  touch only the files the design assigns to a PR, and doing this here would both duplicate a
  designed PR and create rebase conflicts with it. It is also blocked independently: there is
  no API-key route to verify against (§12). This PR makes the request *correctly addressed and
  correctly authenticated*; PR 4 sends it.

### Alternative 2: Send `Authorization: Bearer <key>`, or send both headers

- **What:** Use the `Authorization` header, or belt-and-braces both.
- **Why rejected:** `x-api-key` is the declared canonical name and is checked first, and the
  agent-payments router explicitly refuses `Bearer` as an agent credential. Sending both is
  worse than either alone: `extract_api_key_candidate` returns `None` immediately when
  `x-api-key` is present but non-live, without falling through to `Authorization`, so a
  dual-header client has a silent-failure mode built into it.

### Alternative 3: Enforce `vb_live_` in `Credentials.validate_api_key`

- **What:** Make the prefix a field-level invariant of the model.
- **Why rejected:** That validator runs on every read from the keyring and the restricted
  file, not only on new input. A user holding an old non-live key would get
  `StoredCredentialUnreadable` from `logout` — the one command that exists to remove it. The
  check belongs at the two input boundaries, where the value is still correctable.

### Alternative 4: One shared failure class for both non-live rejections

- **What:** A single `ApiKeyNotLiveFormat` raised from both login input and the environment
  branch.
- **Why rejected:** They need different exit statuses (usage vs authentication) and different
  `trace` text, and the repo already splits this exact pair across channels with
  `InvalidApiKeyInput` and `InvalidEnvironmentApiKey`. Matching that precedent keeps the
  failure catalogue readable.

### Alternative 5: Keep `ApiClient`'s environment fallback and only change the constant

- **What:** The literal minimum — one string edit in two files.
- **Why rejected:** It does not satisfy the ask. "Sends a key the gatekeeper will see" requires
  the header to exist, and the header lives in the constructor path being fixed. It would also
  leave the `ApiOrigin` guard bypassed on the dialing path, which is precisely the "random
  insecure hosts should not be allowed" requirement, and leave program requirement 24 violated.

### Alternative 6: Add a `--header`/auth-scheme configuration option

- **What:** Let a user select `x-api-key` or `Authorization`.
- **Why rejected:** A config knob with one correct value and no caller who would change it.
  The server has one canonical header; making it configurable adds a way to be wrong.

---

## 14. Refinement Record (Phase 5)

An adversarial pass over the original request against the implementation. Items where the
prosecution produced a point the code could not rebut:

- [x] **[Notable] A hand-written credential file bypasses both format guards**
  Expected: "a key that is not a real live key" should read as *wrong format*, never as
  *not logged in*. Actual: the guards sat on the login prompt and `VIDBYTE_API_KEY`, but a
  credential file written by hand crosses neither, and `doctor` reported it as simply
  `present`. Impact: the exact symptom the change exists to remove survived on one path.
  **Resolved** in §6.10 — `doctor` reports `credential_live_format` without echoing the key.

- [x] **[Notable] Two design docs still specified the dead host**
  Expected: leaving the old host anywhere makes the CLI look broken. Actual: the code was
  repointed but `python-cli-research-harness-program.md` still declared
  `api_url: str = "https://api.vidbyte.ai"` as the spec for `ProfileConfig`, and listed it in
  the dependency table. Impact: the next PR implemented from that spec would reintroduce the
  dead host. **Resolved** — both references repointed.

- [x] **[Minor] A sibling doc named the renamed method**
  `harness-runtime-and-cli-scaffold.md` described the dispatch lifecycle as starting at
  `require_api_key`. **Resolved** — renamed to `require_credentials`.

Items the defense rebutted with code, recorded so they are not relitigated:

- *"A fresh install does not actually talk to the real service."* True, and it is the one part
  of the stated done-condition this PR cannot reach. `ApiClient.get`/`post` still raise
  `NotImplementedFeature` because transport is PR 4 of the seven-PR program (§13 Alternative
  1), and it is blocked a second time by the backend: no `/auth/*` or `/harness/*` path is on
  the API-key route table, so every call would 403 before the key was validated (§12). This
  was declared as a Non-Goal in §2 before implementation and reported to the requester, not
  discovered afterwards. What this PR guarantees is that the request is correctly addressed
  and correctly authenticated the moment transport exists.
- *"`whoami` still fails."* Required by FR15 — this change must not make an unimplemented
  command appear to work.
- *"Stored keys are not re-validated against the prefix on read."* Deliberate (§13 Alternative
  3): it would make `logout` unable to clear the very key that needs clearing. `doctor` now
  reports the condition instead.

Carried forward as follow-ups rather than fixed here:

- `_MAX_KEY_CHARACTERS` is declared three times — `lib/auth/credentials.py`,
  `lib/auth/resolver.py`, and as `_MAX_TOKEN_CHARACTERS` in `lib/auth/input.py`. All three
  were touched by this change, but deduplicating them is unrelated to it.
- `scripts/smoke.py` overrides `APPDATA`, which on Windows also relocates the *user* site-packages
  directory. On a machine whose dependencies are user-installed, the smoke gate fails with
  `ModuleNotFoundError` on `main` as well as on this branch. It is an environment interaction,
  not a code defect, and the fix is to run the gate from a virtualenv — but pinning
  `PYTHONNOUSERSITE` or restoring `APPDATA` for the subprocess would make the gate robust.
