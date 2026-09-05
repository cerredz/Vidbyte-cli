# Design Doc: Provider BYOK Login (OpenAI + Claude)

**Status:** Draft
**Author:** Muse Spark
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

Add `vidbyte-cli provider login openai|claude` (and matching `logout`/`whoami`) as BYOK for runtime primitives. Reuses the existing `login` shape — hidden prompt or `--with-token` stdin, verify-before-persist, keyring-first storage scoped by profile — but against provider-native probes (`GET https://api.openai.com/v1/models` with `Authorization: Bearer`, `GET https://api.anthropic.com/v1/models` with `x-api-key` + `anthropic-version: 2023-06-01`). No command ships a `--api-key` argv. Provider keys are independent from `vb_live_` and are consumed only by the future runtime executor when it constructs a provider client; `same-host-ensemble` itself stays credential-free.

---

## 2. Goals & Non-Goals

### Goals

- Two provider login paths: `openai` and `claude`, each with exactly two outcomes: accept (verified and stored) or reject (typed failure, nothing stored).
- Reuse `vidbyte-cli login` invariants: no `--api-key` flag, `SecretStr`, `verify` before `write`, keyring-first with consent-gated `restricted_file` fallback, `VIDBYTE_*`-style env precedence for providers.
- Probe strings/routes match official docs: OpenAI header `Authorization: Bearer <key>` against `https://api.openai.com/v1/models`; Anthropic headers `x-api-key: <key>` + `anthropic-version: 2023-06-01` against `https://api.anthropic.com/v1/models`.
- Modular, provider-extensible code: provider enum, shared storage, per-provider verifier, single command class parameterized by provider.
- Zero new Python dependencies; `httpx` and `keyring` already declared.
- `runtime list`/`doctor` can report provider auth status in a follow-up; this PR ships storage+verification+logout/whoami only.

### Non-Goals

- Wiring keys into `RuntimeExecutor`/`CodexHarnessAgent` execution — that is the future executor PR post `vidbyte-sdk` #409, which will call `ProviderResolver.resolve()` and pass the key as an explicit constructor/env value. This PR stops before process creation, matching `same-host-ensemble`'s inert boundary.
- Accepting OAuth `sk-ant-oat01-` setup-tokens — only `sk-ant-api03-` API keys are verified. OAuth requires `Authorization: Bearer` with `anthropic-beta` handling and is a separate auth mode.
- Supporting `--api-key` argv, `OPENAI_ORG`/`ANTHROPIC_WORKSPACE_ID` headers, or `CODE X` subscription tokens.
- Backend Vidbyte route changes.

---

## 3. Background & Context

- `vidbyte-cli login` (`src/vidbyte_cli/commands/auth/login.py:18`) already enforces verify-before-persist at lines 52-63 and the field guide `typed-failures.md` requires one `CliError` subclass per failure. `AGENTS.md` output contract (`schema_version`/`kind`/`description`/`trace`) applies unchanged.
- Current `vidbyte` runtime scaffold (`docs/design/local-runtime-primitives-scaffold.md` + PR #25 `same-host-ensemble`) deliberately checks no credentials before `EnsembleExecutionNotImplemented`. Provider keys belong at the executor seam, not in `RuntimeLaunchPlanner` — same rationale as Vidbyte login not checking `vidbyte-sdk` keys at plan time.
- No `vidbyte-cli` code has ever hit `api.openai.com` or `api.anthropic.com`. This is the first external auth probe besides `api.vidbyte.ai`.
- Repo is thin transport (`AGENTS.md`): one `ApiClient` already probes Vidbyte on `POST /api/skills/auth/validate` with `x-api-key`. Provider probing must not reuse it — it bakes Vidbyte base URL/auth header/timeout. A separate `ProviderVerifier` owns its own `httpx.Client` (lazy `import httpx` inside method, per `login-key-verification.md` NFR-1: `httpx` adds ~0.14s to `--version` if imported at module scope).
- Docs probed 2026-09-05:
  - OpenAI: `GET https://api.openai.com/v1/models` + `Authorization: Bearer $OPENAI_API_KEY` returns `{object:"list", data:[...]}` on 200, `401 {code:"invalid_api_key"}` on bad key. Keys are `sk-...` / `sk-proj-...`. Ref: `developers.openai.com/api/reference/overview`, `api.openai.com/v1/models`.
  - Anthropic: `GET https://api.anthropic.com/v1/models` + `x-api-key: $ANTHROPIC_API_KEY` + `anthropic-version: 2023-06-01` returns `{data:[{id,...}]}`; legacy `x-api-key` still supported alongside `Authorization`. Keys are `sk-ant-api03-...`. Ref: `platform.claude.com/docs/en/manage-claude/authentication`, `platform.claude.com/docs/en/api/models`. Scope `sk-ant-api02-` is stale; `sk-ant-oat01-` is OAuth, out of scope.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli provider login openai` and `vidbyte-cli provider login claude` MUST exist, each accepting either a hidden prompt or `--with-token` stdin, and no `--api-key` option.
2. Input MUST be bounded 1..4096 chars after `strip()`, rejected as `InvalidApiKeyInput` otherwise, validated locally before any network call.
3. Input format MUST be checked: `openai` keys start with `sk-` (covers `sk-` and `sk-proj-`), `claude` keys start with `sk-ant-` (covers `sk-ant-api03-`). Wrong prefix -> `ProviderKeyNotLiveFormat` without a network call. `is_live_format` MUST NOT be a Pydantic invariant so a stored non-matching key remains removable.
4. Verification MUST probe the canonical liveness endpoint: OpenAI `GET https://api.openai.com/v1/models` with `Authorization: Bearer <key>`; Claude `GET https://api.anthropic.com/v1/models` with `x-api-key: <key>` + `anthropic-version: 2023-06-01`. Must use the resolved timeout and `follow_redirects=False`.
5. Verification MUST NOT retry (probe is non-idempotent for rate-limit purposes) and MUST NOT echo the key, request, or body in errors.
6. Acceptance (HTTP 2xx with valid JSON model list): store via `ProviderCredentialStore.write(profile, provider)` keyring-first, consent-gated file fallback identical to `LoginCommand._fallback_consent`. Report `kind="provider.login"` with `profile`, `provider`, `storage`.
7. Rejection (HTTP 401/403): fail with `ProviderCredentialsRejected` (exit 4), MUST NOT write to any store, MUST NOT clear an existing stored key.
8. Unreachable (DNS/timeout/connection): fail with `ProviderApiUnreachable` (exit 1, retryable), MUST NOT write.
9. Protocol error (non-JSON, wrong content-type, schema mismatch, oversized body): `ProviderApiProtocolError`.
10. Rate limited (429): `ProviderRateLimited` with `Retry-After` hint when numeric; retryable.
11. `provider logout openai|claude` MUST clear keyring + file for that profile+provider, never others. Already-logged-out succeeds.
12. `provider whoami openai|claude` MUST resolve via `ProviderResolver` (env > keyring > file), and if found, re-probe the same endpoint and print non-secret identity (provider, profile, source). If none, `AuthenticationRequired`. Must not make a network call when no credential exists.
13. `--help`/`--version` MUST NOT touch keyring, files, or network; construction stays side-effect free, factories are lazy (`lib/runtime/context.py:56`).
14. Every new failure MUST be a `CliError` subclass in `lib/errors/failures.py` with `code`/`exit_status`/`retryable`/`description`/`trace`/`hint`; no bare `CliError(...)`, no `handler.py` `isinstance` ladder.

### Non-Functional Requirements

- Startup: `import httpx` inside verifying method only.
- Bounded I/O: `+1` over-read on prompt/stdin, 1 MiB cap on probe response (`_MAX_RESPONSE_BYTES=1_048_576`).
- Timeouts: use `ResolvedConfig.request_timeout_seconds` (1..300, default 30). No unbounded wait.
- Secret hygiene: `SecretStr`, `secret_value()` unwrapped only where header is built. `description`/`trace` are static authored text, never echo secrets/backend bodies.

---

## 5. High-Level Design

One new `provider` group under the root program. The group owns three static commands (`login`/`logout`/`whoami`) each parameterized by a `Provider` enum.

```
vidbyte-cli provider login openai|claude [--with-token][--allow-file-fallback]
        | -> CredentialInput.read(...)       # same class as vidbyte login
        | -> ProviderInputValidator.is_live_format(provider, token)  # sk- vs sk-ant-
        | -> ProviderVerifier.verify(provider, credentials)
        |       -> OpenAIVerifier (GET api.openai.com/v1/models)
        |       -> ClaudeVerifier (GET api.anthropic.com/v1/models)
        | -> ProviderCredentialStore.write(profile, provider)
```

Storage mirrors `lib/auth/credentials.py:177` `CredentialStore` but scoped by `provider` instead of `api_url`. Resolver mirrors `CredentialResolver` but with `ProviderSource` and provider-namespaced env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). Future executor resolves via `ApplicationContext.provider_resolver()` and injects the key as an explicit client argument/env dict, never via global `os.environ` mutation.

```
[provider whoami] -> ProviderResolver.resolve(profile, provider)
                  -> if found: ProviderVerifier.verify (same probe)
                  -> whoami: print provider/profile/source
```

```
[ future runtime executor ] -> ProviderResolver.resolve(profile, provider_for_host)
                           -> CodexHarnessAgent(api_key=secret) or env={"OPENAI_API_KEY": secret}
```

---

## 6. Detailed Design

### 6.1 Provider Types

**File(s):** `src/vidbyte_cli/types/provider.py`
**Type:** New

#### What it does

Closed provider enum + typed constant maps for probe strings and env vars. No HTTP, no storage.

#### Interface / API

```python
class Provider(StrEnum):
    OPENAI = "openai"
    CLAUDE = "claude"


PROVIDER_DISPLAY: dict[Provider, str] = ...
PROVIDER_KEY_PREFIXES: dict[Provider, tuple[str, ...]] = {OPENAI: ("sk-",), CLAUDE: ("sk-ant-",)}
PROVIDER_ENV_VARS: dict[Provider, str] = {OPENAI: "OPENAI_API_KEY", CLAUDE: "ANTHROPIC_API_KEY"}
PROBE_TIMEOUT_DEFAULT: float = 10.0  # used only when ReconciledConfig timeout is unset in tests
```

#### Edge Cases & Error Handling

- `Provider("openai")` coercion is case-sensitive via `click.Choice`; no extra normalization needed.

### 6.2 Provider Credential Model & Stores

**File(s):** `src/vidbyte_cli/lib/auth/provider_credentials.py`
**Type:** New

#### What it does

Secret-safe credential + keyring-first / file-fallback document, scoped by `profile@provider` (not `profile@host`, not `api_url`). Reuses `KeyringBackend` protocol and `AtomicFileWriter` already in the repo. Single import-safe place for `ProviderScope`, `ProviderCredentialStore`.

#### Interface / API

```python
class ProviderCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Provider
    api_key: SecretStr
    @field_validator("api_key") def validate_api_key(...) -> SecretStr: ...
    def secret_value(self) -> str: ...
    @classmethod def is_live_format(cls, provider: Provider, value: str) -> bool:
        # provider-specific prefix check against PROVIDER_KEY_PREFIXES

class ProviderCredentialStorage(StrEnum): KEYRING = "keyring"; RESTRICTED_FILE = "restricted_file"

class ProviderDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    entries: dict[str, SecretStr] = Field(default_factory=dict)  # device1@openai -> SecretStr

class FileProviderStore:
    def read(self, profile: str, provider: Provider) -> ProviderCredentials | None: ...
    def write(self, credentials: ProviderCredentials, profile: str, provider: Provider) -> None: ...
    def clear(self, profile: str, provider: Provider) -> bool: ...

class ProviderCredentialStore:
    def __init__(self, keyring_store: KeyringProviderStore | None = None, file_store: FileProviderStore | None = None, paths: VidbytePaths | None = None) -> None: ...
    def available(self) -> bool: ...
    def read(self, profile: str, provider: Provider) -> ProviderCredentials | None: ...
    def write(self, credentials: ProviderCredentials, profile: str, provider: Provider, *, allow_file_fallback: bool = False) -> ProviderCredentialStorage: ...
    def clear(self, profile: str, provider: Provider) -> bool: ...
```

Evidence for prefix: `sk-` matches `sk-proj-` and `sk-svcacct-`; `sk-ant-` matches `sk-ant-api03-` (Ref session search: Anthropic docs `sk-ant-api03-`).

#### Logic / Algorithm

1. `ProviderScope(profile, provider).account` -> `f"{profile}@{provider.value}"` (lower, no port/origin nuance).
2. Keyring service name `_PROVIDER_SERVICE = "vidbyte-cli-provider"` — distinct from `_SERVICE_NAME="vidbyte-cli"` so Vidbyte and provider keys never collide.
3. `read` -> keyring `get_password(service, account)` else file document lookup; if file missing -> `None`, if corrupt -> `StoredProviderCredentialUnreadable` subclass.
4. `write` -> if `keyring.available()` write+readback verification; else if `allow_file_fallback` encode JSON with `entries[account]=api_key.get_secret_value()` via `AtomicFileWriter`; else `NoApprovedProviderStore`.

#### Edge Cases & Error Handling

- `schema_version !=1` -> `StoredProviderCredentialUnreadable`.
- Oversized file `>1_000_000` bytes -> same failure.
- Symlink on credential file path: `AtomicFileWriter` already guards; reuse.
- No `_is_tty` needed here — consent lives in the command layer like `LoginCommand._fallback_consent`.

### 6.3 Provider Input + Verification

**File(s):** `src/vidbyte_cli/lib/auth/provider_input.py`, `src/vidbyte_cli/lib/auth/provider_verifier.py`
**Type:** New (two small files, one protocol + two verifiers is clearer than one god file)

#### What it does

`ProviderInputValidator` narrows already-bounded token by provider prefix (`sk-` vs `sk-ant-`) without a network call. `ProviderVerifier` proves the token against the live provider endpoint, returning a non-secret identity for `whoami`.

#### Interface / API

```python
class ProviderCredentialInput:
    def read(self, *, from_stdin: bool) -> ProviderCredentials:  # provider passed at construction
        # delegates to CredentialInput.read's no-input/terminal logic, then validates prefix

class ProviderVerifier(Protocol):
    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity: ...

class ProviderIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Provider
    verified: bool = True

class OpenAIVerifier:
    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # GET https://api.openai.com/v1/models, Authorization: Bearer <key>, Accept: application/json

class ClaudeVerifier:
    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # GET https://api.anthropic.com/v1/models, x-api-key: <key>, anthropic-version: 2023-06-01
```

#### Logic / Algorithm

`OpenAIVerifier.verify`:
1. `import httpx` locally.
2. `with httpx.Client(timeout=timeout, follow_redirects=False, limits=Limits(...)) as client:` -> `client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}", "Accept":"application/json"})`
3. `2xx` + `Content-Type` contains `json` + `len(content)<=1MiB` + `json.loads` + `model.model_validate({"provider":..., "verified":True})` -> success. Treat only `200-299` as accept.
4. `401/403` -> `ProviderCredentialsRejected` (exit 4, code AUTH_REQUIRED). `429` -> `ProviderRateLimited`. `400/422` -> `ProviderRequestRejected`. `5xx` -> retryable `ProviderApiUnreachable` after retries settled. Transport `httpx.HTTPError` -> `ProviderApiUnreachable`. Non-JSON/oversized -> `ProviderApiProtocolError`.

`ClaudeVerifier.verify` same but headers `{"x-api-key": key, "anthropic-version":"2023-06-01", "Accept":"application/json"}` and host `https://api.anthropic.com/v1/models`. The fixed `anthropic-version: 2023-06-01` is the current required version per `platform.claude.com/docs/en/manage-claude/authentication` — the search excerpts confirm requests without it are rejected with `invalid_request_error`. Do not use `Authorization: Bearer` for `sk-ant-` keys.

A factory `ProviderVerifier.for_provider(provider)` returns the correct verifier; the command does not branch on `if provider`.

#### Edge Cases & Error Handling

- `x-api-key` vs `Authorization: Bearer` must be exact — Anthropic supports both for OAuth but `sk-ant-` expects `x-api-key`; sending both leaks the key twice.
- Response body shape: OpenAI `{object:"list", data:[{id,...}]}`; Anthropic `{data:[{id,...}]}`. Verifier validates only that `data` is a list on decode; strict model validation would couple to provider churn. Minimal `ProviderIdentity` is enough for the two-path accept/reject contract the user asked for.
- Never include response body in `message`/`hint`; body may contain the mistyped key.

### 6.4 Provider Resolver

**File(s):** `src/vidbyte_cli/lib/auth/provider_resolver.py`
**Type:** New

#### What it does

Implements `env > keyring > file` for provider keys, scoped by `profile+provider`.

#### Interface / API

```python
class ProviderSource(StrEnum): ENVIRONMENT="environment"; KEYRING="keyring"; RESTRICTED_FILE="restricted_file"

@dataclass(frozen=True) class ResolvedProviderCredential: credentials: ProviderCredentials; source: ProviderSource

class ProviderResolver:
    def __init__(self, store: ProviderCredentialStore, environment: Mapping[str,str]) -> None: ...
    def resolve(self, profile: str, provider: Provider) -> ResolvedProviderCredential | None: ...
```

#### Logic / Algorithm

1. Check `environment[PROVIDER_ENV_VARS[provider]]` — if present, `strip()`, bounds `1..4096`, prefix check `is_live_format`; if set-but-invalid -> `InvalidProviderEnvironmentKey(provider, var)`. If valid -> `ENVIRONMENT`.
2. Else `store.keyring.read` -> `KEYRING`; else `store.file.read` -> `RESTRICTED_FILE`; else `None`.

Env name per provider: `OPENAI_API_KEY` for `openai`, `ANTHROPIC_API_KEY` for `claude` (per official env var docs). No `CLAUDE_API_KEY` alias; alias would widen secret precedence silently.

### 6.5 Commands

**File(s):** `src/vidbyte_cli/commands/provider/__init__.py`, `src/vidbyte_cli/commands/provider/login.py`, `src/vidbyte_cli/commands/provider/logout.py`, `src/vidbyte_cli/commands/provider/whoami.py`
**Type:** New

#### What it does

Thin orchestration like `commands/auth/*`: resolve config, acquire input, verify, persist, render `OutputDocument`.

#### Interface / API

```python
class ProviderLoginCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(
        self,
        context: ApplicationContext,
        provider: str,
        with_token: bool,
        allow_file_fallback: bool,
    ) -> None: ...


class ProviderLogoutCommand: ...


class ProviderWhoamiCommand: ...
```

Click surface:
```
vidbyte-cli provider login openai|claude [--with-token] [--allow-file-fallback]
vidbyte-cli provider logout openai|claude
vidbyte-cli provider whoami openai|claude
```

#### Logic / Algorithm

`ProviderLoginCommand.execute`:
1. `config = context.resolved_config()`
2. `input = ProviderCredentialInput(context.streams, context.output().terminal, no_input=options.no_input, provider=Provider(provider))`
3. `creds = input.read(from_stdin=with_token)` — reuses `CredentialInput`'s `stdin.read(4097)` + `getpass` + `trim` + `bounds` + prefix check `is_live_format`.
4. `context.provider_verifier(provider).verify(creds)` — raises typed failure before any write.
5. `fallback = self._fallback_consent(context, allow_file_fallback)` — identical to `LoginCommand._fallback_consent`: `keyring.available -> False`, else `explicitly_allowed -> True`, else `no_input/interactive -> FileFallbackNotApproved`, else `confirm`.
6. `context.migration().migrate_if_needed()` — reuse (no provider legacy migration needed now).
7. `storage = context.provider_store().write(creds, config.profile, Provider(provider), allow_file_fallback=fallback)`
8. `context.output().result(OutputDocument(kind="provider.login", data={profile, provider, storage}), human)`

`ProviderWhoamiCommand.execute`: `resolve` via `ProviderResolver`; if `None` -> `ProviderAuthenticationRequired(provider)` (reuses `AuthenticationRequired` shape with provider hint); else `verify` then emit `kind="provider.whoami"` with `provider/profile/source/verified`.

`ProviderLogoutCommand.execute`: `context.provider_store().clear(profile, provider)`; emit `kind="provider.logout"`.

#### Edge Cases & Error Handling

- `--with-token` missing on noninteractive -> `NoninteractiveLoginRequiresToken` alias `NoninteractiveProviderLoginRequiresToken` subclass.
- `OPENAI_API_KEY` empty when set -> `InvalidProviderEnvironmentKey` — not a fallthrough to keyring, same rationale as `InvalidEnvironmentApiKey`.

### 6.6 ApplicationContext Wiring

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

Adds lazy factories parallel to existing credential factories:

```python
def provider_store(self) -> ProviderCredentialStore: ...
def provider_resolver(self) -> ProviderResolver: ...
def provider_verifier(
    self, provider: Provider
) -> ProviderVerifier: ...  # returns OpenAIVerifier/ClaudeVerifier
```

No eager `httpx` import; no network in `configure()` or `register_all_commands`.

### 6.7 Failure Classes

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

Add per-provider typed failures (each is a distinct `CliError` subclass, following `typed-failures.md`):

- `ProviderKeyNotLiveFormat(provider)` — prefix mismatch before network.
- `ProviderCredentialsRejected(provider)` — 401/403.
- `ProviderApiUnreachable(provider, cause)` — transport failure, retryable.
- `ProviderApiProtocolError(provider)` — undecodable 2xx.
- `ProviderRateLimited(provider, retry_after)`.
- `ProviderRequestRejected(provider)` — 400/422.
- `ProviderStoreUnavailable(provider, cause)`.
- `NoApprovedProviderStore(provider)` — verified but nowhere to persist without consent.
- `StoredProviderCredentialUnreadable(cause)`.
- `ProviderAuthenticationRequired(provider)` — whoami/logic close sibling of `AuthenticationRequired`.

Each carries `code=AUTH_REQUIRED` or `API_UNAVAILABLE` consistently with the `vidbyte` equivalents, and `hint` points at `provider login <provider>`.

---

## 7. Data Model Changes

### 7.1 CLI-Local Provider Document

**Change type:** New file on disk, versioned.

Path: `{config_dir}/provider-credentials.json` (via `VidbytePaths.provider_credentials_file()`, sibling of `credentials_file()`). Schema `schema_version:1` with `entries: { "default@openai": "<secret>", "default@claude":"<secret>" }`. `SECRET` values are `SecretStr` in memory, unwrapped only in `_encode`.

**Migration strategy:** No migration from legacy path. First login creates the file via `AtomicFileWriter.write`. Logout clears just the addressed entry. `clear_legacy` not needed.

---

## 8. API Changes

No Vidbyte backend API changes.

Provider probes (not Vidbyte-controlled):

- `GET https://api.openai.com/v1/models` — header `Authorization: Bearer <key>` — expected `200 {object:"list", data:[{id,...}]}` on success. Ref: `developers.openai.com/api/reference/overview`.
- `GET https://api.anthropic.com/v1/models` — headers `x-api-key: <key>` + `anthropic-version: 2023-06-01` — expected `200 {data:[{id,...}]}`. Ref: `platform.claude.com/docs/en/api/models`, `platform.claude.com/docs/en/manage-claude/authentication`.

Failure shapes are provider-specific; the client classifies only by status per §6.3.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/provider-byok-login.md` | This design doc |
| CREATE | `src/vidbyte_cli/types/provider.py` | Provider enum + probe/env maps |
| CREATE | `src/vidbyte_cli/lib/auth/provider_credentials.py` | `ProviderCredentials` + `ProviderScope` + `ProviderDocument` |
| CREATE | `src/vidbyte_cli/lib/auth/provider_store.py` | `FileProviderStore` + `KeyringProviderStore` + `ProviderCredentialStore` |
| CREATE | `src/vidbyte_cli/lib/auth/provider_resolver.py` | Env>keyring>file provider resolver |
| CREATE | `src/vidbyte_cli/lib/auth/provider_verifier.py` | `ProviderVerifier` protocol + `OpenAIVerifier`/`ClaudeVerifier` |
| CREATE | `src/vidbyte_cli/lib/auth/provider_input.py` | Provider-aware hidden-prompt/stdin input + prefix check |
| CREATE | `src/vidbyte_cli/commands/provider/__init__.py` | Export provider commands |
| CREATE | `src/vidbyte_cli/commands/provider/login.py` | `provider login openai|claude` |
| CREATE | `src/vidbyte_cli/commands/provider/logout.py` | `provider logout` |
| CREATE | `src/vidbyte_cli/commands/provider/whoami.py` | `provider whoami` |
| MODIFY | `src/vidbyte_cli/commands/__init__.py` | Register `provider` group |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Add provider factories |
| MODIFY | `src/vidbyte_cli/lib/config/paths.py` | Add `provider_credentials_file()` |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add provider failure subclasses |
| MODIFY | `README.md` | Document provider commands |
| MODIFY | `docs/architecture.md` | Document provider auth seam |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|-------------------|---------|------|
| `httpx` | `>=0.27,<1` (exists) | Provider probes | No new dep; lazy import inside `verify` |
| `keyring` | `>=25.2` (exists) | Provider key storage | Reuses existing service, new service name |
| `api.openai.com` | `GET /v1/models` | OpenAI probe | External; rate-limited per key |
| `api.anthropic.com` | `GET /v1/models` | Claude probe | External; requires fixed `anthropic-version` header |

---

## 11. Rollout & Deployment

- Ships independently of runtime executor; executor will call `provider_resolver` when it exists, otherwise raise `ProviderAuthenticationRequired` (or honor env var).
- No feature flag; additive CLI surface, `provider --help` is side-effect free.
- Rollback: remove `provider` group registration and its auth factories; file `provider-credentials.json` stays inert until next login.

---

## 12. Open Questions

- [ ] Should `sk-ant-oat01-` OAuth setup-tokens be accepted as valid `claude` input? Currently rejected (require `sk-ant-`). OAuth uses `Authorization: Bearer` not `x-api-key`, so the probe header would differ.
- [ ] Should `provider whoami` report the mask/redaction of the stored key prefix (e.g., `sk-ant-***`) or strictly the presence/source? Current doc says source only to avoid any secret hint leakage.
- [ ] Exact `ANTHROPIC_API_KEY` vs `CLAUDE_API_KEY` env naming: doc sources show `ANTHROPIC_API_KEY` as canonical (`client = Anthropic()` reads `ANTHROPIC_API_KEY`). Use that, not `CLAUDE_API_KEY`.

---

## 13. Testing Plan

Harness: `scripts/test-provider-byok-login.py` against loopback `http.server.ThreadingHTTPServer` for probes (bound to `127.0.0.1:0`), injected `KeyringBackend` fake with controllable `priority`, temp `VidbytePaths` under `tmp_path`. Exercises real `httpx` transport; keyring fake to avoid OS dialog.

### Unit Tests — ProviderInput / is_live_format

- [Edge Case] Empty stdin after trim -> `InvalidApiKeyInput`, no network.
- [Edge Case] 4097 chars -> `InvalidApiKeyInput` (over bound).
- [Hidden Assumption] `sk-ant-...` passed as `openai` -> `ProviderKeyNotLiveFormat` without hitting OpenAI host (provider-specific prefix).
- [Hidden Assumption] `sk-proj-...` passed as `claude` -> `ProviderKeyNotLiveFormat`.
- [Silent Failure] `extra="forbid"` rejects `ProviderCredentials(provider=OPENAI, api_key=SecretStr(...), extra="oops")` — prevents stray fields reaching storage.
- [Edge Case] Whitespace-only token -> `InvalidApiKeyInput`.

### Unit Tests — Verifiers (OpenAI + Claude parameterized)

- [Edge Case] 200 valid JSON model list -> returns `ProviderIdentity(verified=True)`.
- [Silent Failure] 200 `{object:"list", data:[]}` vs missing `data` — verifier must not accept empty object as valid without `data` check.
- [Silent Failure] Sends exactly one auth header per provider: OpenAI asserts `Authorization: Bearer <key>` and asserts absence of `x-api-key`; Claude asserts `x-api-key` + `anthropic-version: 2023-06-01` and absence of `Authorization: Bearer <key>`.
- [Hidden Failure] Does not follow `302` to another origin — target server receives zero requests.
- [Hidden Failure] Transport timeout -> `ProviderApiUnreachable` not `ProviderCredentialsRejected` (highest-value distinction).
- [Edge Case] 401 -> `ProviderCredentialsRejected` exit 4, nothing stored.
- [Edge Case] 403 -> same as 401 (Anthropic `IP_BLOCKED` maps identically).
- [Edge Case] 429 with `Retry-After: 60` -> `ProviderRateLimited` hint carries `60`.
- [Edge Case] 200 `content-type: text/html` -> `ProviderApiProtocolError` (captive portal guard).
- [Edge Case] Body `>1_048_576` -> `ProviderApiProtocolError`.
- [Edge Case] `anthropic-version` missing would cause Claude 400 — assert the header is sent exactly `2023-06-01`.
- [Silent Failure] No response body quoted in any failure `message`/`description`.

### Integration Tests — Login through store

- [Hidden Assumption] Stores after 200 only — keyring file contains `default@openai` after accept.
- [Silent Failure] Writes nothing to keyring nor file on 401.
- [Silent Failure] Writes nothing on transport failure.
- [Silent Failure] Second failed login leaves existing stored key intact (no corruption).
- [Hidden Failure] Sends exactly one probe per login (no retry — budget).
- [Hidden Assumption] `--allow-file-fallback` on headless host writes to `provider-credentials.json` with `0600`-like restricted permissions via `AtomicFileWriter`.

---

## 14. Alternatives Considered

### Alternative 1: Reuse Vidbyte CredentialStore service name

- What: store provider keys in same `vidbyte-cli` keyring entries keyed by `default@api.openai.com`.
- Why rejected: conflates Vidbyte and provider namespaces; a `provider logout openai` would risk clearing a Vidbyte key if the scope string collides, and `VIDBYTE_API_KEY` env semantics would leak.

### Alternative 2: Shell out to `codex login` / `claude login`

- What: delegate auth to the provider's own CLI config files.
- Why rejected: those CLIs store keys in different formats/paths per OS and update them without a stable read API; `vidbyte-cli` would then depend on parsing `~/.codex/config.toml` or `~/.claude/.credentials.json` (OAuth-locked, not portable). Verified probe against the API is the only stable contract.

### Alternative 3: One surface `vidbyte-cli provider login --key <value>` argv

- What: accept the key as a direct flag.
- Why rejected: violates the repo's own `login:3` invariant — secret in argv leaks to `ps`/history/CI logs, and no amount of caller care takes it back. Stdin + hidden prompt are the only two channels the repo sanctions (see `lib/auth/input.py:1`).

---

## 15. Rollout Risks

- Provider endpoints are external; probe wording must not expose them as Vidbyte infrastructure. Failures render provider-specific hints but keep request/response bodies private.
- Key prefix validation is intentionally loose (`sk-` not `sk-proj-` exact) to avoid rejecting future `sk-svcacct-` project-scoped keys. Documented as `sk-ant-` for Claude to match current `sk-ant-api03-`.

