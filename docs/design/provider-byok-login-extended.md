# Design Doc: Provider BYOK Login Extended (Grok, DeepSeek, GLM, Muse)

**Status:** Draft
**Author:** Muse Spark
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

Extend `vidbyte-cli provider login|logout|whoami` beyond `openai` and `claude` to four additional BYOK providers: `grok` (xAI), `deepseek` (DeepSeek), `glm` (Zhipu GLM / Z.AI), and `muse` (Meta Muse Spark). The change reuses the exact invariants from `provider-byok-login` - hidden prompt or `--with-token` stdin, verify-before-persist, keyring-first with consent-gated `restricted_file` fallback, profile-scoped `profile@provider` storage, and `env > keyring > file` resolution - but adds per-provider probe strings, env var names, and prefix checks. No new dependencies, no backend Vidbyte routes, and no wiring into the runtime executor yet.

---

## 2. Goals & Non-Goals

### Goals

- Four new provider choices under the existing `provider` group: `grok`, `deepseek`, `glm`, `muse`, each with `login`, `logout`, `whoami` and the same two outcomes: accept (verified and stored) or reject (typed failure, nothing stored).
- Preserve every `vidbyte-cli login` invariant: no `--api-key` argv, `SecretStr`, verify before write, lazy `import httpx`, bounded I/O, `follow_redirects=False`, and no secret echo in errors.
- Each provider probes its canonical liveness endpoint with its documented auth header and is classified identically (401/403 -> rejected, 429 -> rate limited, 5xx/transport -> unreachable, non-JSON/oversized/missing `data` -> protocol error).
- Storage remains the single `provider-credentials.json` file and the `vidbyte-cli-provider` keyring service; new providers are new keys in the same document, not a migration.
- Extensible code: provider enum, shared storage/resolver, per-provider verifier, factory keeps command branching closed.

### Non-Goals

- Wiring keys into `RuntimeExecutor` or `CodexHarnessAgent` execution - same boundary as the original doc. The executor will call `ProviderResolver.resolve()` in a later PR.
- Supporting provider OAuth flows, org/workspace headers, or subscription tokens.
- Accepting alternative base URLs per invocation (e.g. `open.bigmodel.cn` vs `api.z.ai` both for GLM) - one canonical probe per provider.
- Adding a generic `--api-key` flag or exposing the key value in `whoami` output.

---

## 3. Background & Context

- `provider-byok-login` (merged as `1406fe5`, `docs/design/provider-byok-login.md`) already ships `openai` and `claude` with the full stack: `src/vidbyte_cli/types/provider.py:12` enum, `src/vidbyte_cli/lib/auth/provider_credentials.py:42` prefix check, `src/vidbyte_cli/lib/auth/provider_verifier.py:42` base verifier, `src/vidbyte_cli/lib/auth/provider_store.py:18` keyring/file facade, `src/vidbyte_cli/lib/auth/provider_resolver.py:18` env precedence, and `src/vidbyte_cli/commands/provider/*` thin commands. `AGENTS.md` output contract and `field-guide/vidbyte-cli/typed-failures.md` one-subclass-per-failure rule apply unchanged.
- Docs probed 2026-09-05 for the four new providers:
  - **Grok (xAI):** `GET https://api.x.ai/v1/models` with `Authorization: Bearer $XAI_API_KEY` returns `{object:"list", data:[{id,...}]}`. Ref: `docs.x.ai/developers/quickstart` (exports `XAI_API_KEY`), `docs.x.ai/developers/rest-api-reference/inference/models` (GET /v1/models). No stable public prefix; treat as opaque.
  - **DeepSeek:** `GET https://api.deepseek.com/models` (alias `/v1/models`) with `Authorization: Bearer $DEEPSEEK_API_KEY` returns `{object:"list", data:[{id: "deepseek-v4-flash", object:"model", owned_by:"deepseek"}]}`. Ref: `api-docs.deepseek.com/api/list-models`, `api-docs.deepseek.com/api/deepseek-api` (Bearer auth). Keys are `sk-` like OpenAI.
  - **GLM (Z.AI / Zhipu):** `POST https://api.z.ai/api/paas/v4/chat/completions` is the documented chat endpoint; the OpenAI-compatible `GET https://api.z.ai/api/paas/v4/models` is the liveness probe (same shape as the other OpenAI-compatible providers). Alternate host `https://open.bigmodel.cn/api/paas/v4/` exists for mainland China but one probe suffices. Auth is `Authorization: Bearer $ZAI_API_KEY`. Ref: `docs.z.ai/api-reference/introduction`, `docs.z.ai/guides/develop/http/introduction`. No stable prefix.
  - **Muse (Meta):** `GET https://api.meta.ai/v1/models` with `Authorization: Bearer $MODEL_API_KEY` returns `data` list. Ref: `ai.developer.meta.com/docs/api-reference/models/list-models`, `ai.developer.meta.com/docs/authentication`, `dev.meta.ai/docs/authentication`. Keys are `LLM|...`.
- Existing `ProviderVerifier` owns its own `httpx.Client` per verification (lazy import inside method per `login-key-verification.md` NFR-1). Reuse the same pattern; do not reuse `ApiClient` which bakes Vidbyte base URL/timeout.
- Keyring service stays `vidbyte-cli-provider` so new providers do not collide with Vidbyte keys or with each other; scoping is `profile@provider.value`.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli provider login grok|deepseek|glm|muse` MUST exist alongside `openai|claude`, accepting hidden prompt or `--with-token` stdin, and no `--api-key` option. Choices are case-sensitive via `click.Choice`.
2. Input MUST be bounded 1..4096 chars after `strip()`, rejected as `InvalidProviderApiKeyInput` otherwise, before any network call.
3. Input format MUST be checked via `ProviderCredentials.is_live_format(provider, value)`:
   - `grok`: no prefix filter (opaque key) - any non-empty 1..4096 passes prefix stage; alternative is `xai-` prefix but not documented, so skip strict check.
   - `deepseek`: `sk-` prefix required (and not `sk-ant-`), mirroring OpenAI; wrong prefix -> `ProviderKeyNotLiveFormat`.
   - `glm`: no prefix filter (opaque).
   - `muse`: `LLM|` prefix required; wrong prefix -> `ProviderKeyNotLiveFormat`. `is_live_format` MUST NOT be a Pydantic validator so a stored non-matching key remains removable.
4. Verification MUST probe the canonical liveness endpoint:
   - `grok`: `GET https://api.x.ai/v1/models` with `Authorization: Bearer <key>`.
   - `deepseek`: `GET https://api.deepseek.com/v1/models` with `Authorization: Bearer <key>` (canonical `/v1/models`; `/models` also serves but `/v1/models` matches the other providers and the docs example).
   - `glm`: `GET https://api.z.ai/api/paas/v4/models` with `Authorization: Bearer <key>`.
   - `muse`: `GET https://api.meta.ai/v1/models` with `Authorization: Bearer <key>`.
   All probes use `Accept: application/json`, `follow_redirects=False`, and the resolved timeout (default 15s in the verifier, aligning with `provider_verifier.py:108`).
5. Verification MUST NOT retry and MUST NOT echo key or body. Classification: 401/403 -> `ProviderCredentialsRejected` (exit 4), 429 -> `ProviderRateLimited` with `Retry-After` hint, 5xx/transport -> `ProviderApiUnreachable` (retryable), 400/404/409/422 and other non-2xx -> `ProviderRequestRejected`, empty/oversized/non-JSON/missing `data` list -> `ProviderApiProtocolError`.
6. On 2xx with valid JSON `data` list: store via `ProviderCredentialStore.write(profile, provider)` keyring-first, consent-gated file fallback. Emit `kind="provider.login"` with `profile`, `provider`, `storage`.
7. On rejection (401/403) or any failure: MUST NOT write, MUST NOT clear an existing stored key for any provider.
8. `provider logout <provider>` MUST clear keyring + file for that `profile@provider` only; already-logged-out succeeds.
9. `provider whoami <provider>` MUST resolve via `ProviderResolver` (env > keyring > file) without a network call when no credential exists; if found, re-probe the same endpoint and emit `kind="provider.whoami"` with `provider`, `profile`, `verified`, `credential_source`. If none -> `ProviderAuthenticationRequired`.
10. `--help`/`--version` MUST NOT touch keyring, files, or network; factories stay lazy in `lib/runtime/context.py`.
11. Every new failure remains a `CliError` subclass in `lib/errors/failures.py` - reuse the existing provider failures where the semantics are identical (rejected/unreachable/protocol/rate-limited/request-rejected/store-unavailable/no-approved-store/authentication-required) and they already carry provider name in the message. No new failure class is needed unless a distinct code path appears (prefix mismatch already uses `ProviderKeyNotLiveFormat`).
12. Env var precedence is provider-specific: `XAI_API_KEY` for grok, `DEEPSEEK_API_KEY` for deepseek, `ZAI_API_KEY` for glm, `MODEL_API_KEY` for muse. Set-but-invalid (empty, oversized, wrong prefix) MUST raise `InvalidProviderEnvironmentKey(provider, var)` not fall through to keyring.

### Non-Functional Requirements

- Startup: `import httpx` inside `verify` only.
- Bounded I/O: `+1` over-read on prompt/stdin, 1 MiB cap on probe response.
- Timeouts: `ResolvedConfig.request_timeout_seconds` when wired; verifiers currently use 15.0s literal - keep until the config timeout is plumbed.
- Secret hygiene: `SecretStr`, `secret_value()` unwrapped only where header is built. `description`/`trace` static, never echo backend bodies.

---

## 5. High-Level Design

No new command surface beyond the enum expansion. The `provider` group already owns `login`/`logout`/`whoami` parameterized by `Provider`; adding four enum members extends the `click.Choice` automatically.

```
vidbyte-cli provider login grok|deepseek|glm|muse [--with-token][--allow-file-fallback]
        | -> ProviderCredentialInput.read(...)  # bounds + is_live_format(provider)
        | -> verifier_for_provider(provider).verify(credentials)
        |       -> GrokVerifier     (GET https://api.x.ai/v1/models, Bearer)
        |       -> DeepSeekVerifier (GET https://api.deepseek.com/v1/models, Bearer)
        |       -> GlmVerifier      (GET https://api.z.ai/api/paas/v4/models, Bearer)
        |       -> MuseVerifier     (GET https://api.meta.ai/v1/models, Bearer)
        | -> ProviderCredentialStore.write(profile, provider)  # keyring -> file
```

Resolver chain stays `env > keyring > file` with `PROVIDER_ENV_VARS[provider]` mapping. Storage stays `vidbyte-cli-provider` service + `provider-credentials.json` document - new providers are new keys like `default@grok`, `default@deepseek`, `default@glm`, `default@muse`.

```
[provider whoami] -> ProviderResolver.resolve(profile, provider) -> if found: verifier_for_provider(provider).verify() -> OutputDocument kind="provider.whoami"
[future executor] -> ProviderResolver.resolve(profile, provider_for_host) -> client(api_key=secret)
```

---

## 6. Detailed Design

### 6.1 Provider Types

**File(s):** `src/vidbyte_cli/types/provider.py`
**Type:** Modified

#### What it does

Closed enum + typed constant maps for probe strings, env vars, display names, and key prefixes. No HTTP, no storage.

#### Interface / API

```python
class Provider(StrEnum):
    OPENAI = "openai"
    CLAUDE = "claude"
    GROK = "grok"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MUSE = "muse"


PROVIDER_KEY_PREFIXES: dict[Provider, tuple[str, ...]] = {
    OPENAI: ("sk-",),
    CLAUDE: ("sk-ant-",),
    DEEPSEEK: ("sk-",),
    MUSE: ("LLM|",),
    GROK: (),
    GLM: (),
}
PROVIDER_ENV_VARS: dict[Provider, str] = {
    OPENAI: "OPENAI_API_KEY",
    CLAUDE: "ANTHROPIC_API_KEY",
    GROK: "XAI_API_KEY",
    DEEPSEEK: "DEEPSEEK_API_KEY",
    GLM: "ZAI_API_KEY",
    MUSE: "MODEL_API_KEY",
}
PROVIDER_DISPLAY: dict[Provider, str] = {
    OPENAI: "OpenAI",
    CLAUDE: "Claude",
    GROK: "Grok",
    DEEPSEEK: "DeepSeek",
    GLM: "GLM",
    MUSE: "Muse",
}
PROVIDER_PROBE_URLS: dict[Provider, str] = {
    OPENAI: "https://api.openai.com/v1/models",
    CLAUDE: "https://api.anthropic.com/v1/models",
    GROK: "https://api.x.ai/v1/models",
    DEEPSEEK: "https://api.deepseek.com/v1/models",
    GLM: "https://api.z.ai/api/paas/v4/models",
    MUSE: "https://api.meta.ai/v1/models",
}
```

#### Edge Cases & Error Handling

- `Provider("grok")` coercion remains case-sensitive via `click.Choice`; no extra normalization.
- Empty prefix tuple (`GROK`, `GLM`) means `is_live_format` returns `True` for any non-empty bounded string - intentional because neither provider publishes a stable prefix.

### 6.2 Provider Credential Model

**File(s):** `src/vidbyte_cli/lib/auth/provider_credentials.py`
**Type:** Modified

#### What it does

Secret-safe credential with bounds check and provider-specific prefix check. No storage.

#### Interface / API

```python
class ProviderCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Provider
    api_key: SecretStr
    @field_validator("api_key") def validate_api_key(...) -> SecretStr: ...
    @classmethod def is_live_format(cls, provider: Provider, value: str) -> bool: ...
    def secret_value(self) -> str: ...
```

#### Logic / Algorithm

- `is_live_format` expands to:
  1. `CLAUDE` -> `value.startswith("sk-ant-")`
  2. `OPENAI` -> `value.startswith("sk-") and not value.startswith("sk-ant-")`
  3. `DEEPSEEK` -> same as `OPENAI` (`sk-` and not `sk-ant-`) since DeepSeek issues `sk-` keys
  4. `MUSE` -> `value.startswith("LLM|")`
  5. `GROK` / `GLM` -> `True` (any bounded non-empty string is live format; env/file resolution still bounds-checks length)
  6. Fallback -> `any(value.startswith(p) for p in PROVIDER_KEY_PREFIXES.get(provider, ()))`

#### Edge Cases & Error Handling

- `is_live_format` is not a Pydantic validator so a stored key that later fails a stricter prefix remains readable and clearable.
- `validate_api_key` keeps 1..4096 bounds; oversize is rejected before network.

### 6.3 Provider Input

**File(s):** `src/vidbyte_cli/lib/auth/provider_input.py`
**Type:** Modified (no structural change)

#### What it does

Acquires one provider token via hidden prompt or stdin, then delegates to `ProviderCredentials.is_live_format(provider, token)` for the provider-specific prefix gate.

#### Logic / Algorithm

No code change beyond the provider argument already being parameterized. The `GROK` and `GLM` paths will pass any bounded token; `DEEPSEEK` and `MUSE` will enforce their prefixes and raise `ProviderKeyNotLiveFormat(provider)` without a network call.

### 6.4 Provider Verification

**File(s):** `src/vidbyte_cli/lib/auth/provider_verifier.py`
**Type:** Modified

#### What it does

Proves a candidate key against its native endpoint, sharing transport and classification in `_BaseProviderVerifier`. Four new verifiers are bearer-only, so they reuse the same shape as `OpenAIVerifier`.

#### Interface / API

```python
class GrokVerifier(_BaseProviderVerifier):
    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity: ...
    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]: ...


class DeepSeekVerifier(_BaseProviderVerifier): ...


class GlmVerifier(_BaseProviderVerifier): ...


class MuseVerifier(_BaseProviderVerifier): ...


def verifier_for_provider(provider: Provider) -> ProviderVerifier: ...
```

#### Logic / Algorithm

Each verifier:

1. `import httpx` locally.
2. `self._probe(credentials, timeout_seconds=15.0)` where `_probe` builds `{"Accept": "application/json", **self._headers(credentials)}` and `client.get(PROVIDER_PROBE_URLS[provider], headers=headers)` with `follow_redirects=False`.
3. Returns `ProviderIdentity(provider=credentials.provider)` on success.

`_headers` per provider:

- `GrokVerifier`: `{"Authorization": f"Bearer {credentials.secret_value()}"}`
- `DeepSeekVerifier`: `{"Authorization": f"Bearer {credentials.secret_value()}"}`
- `GlmVerifier`: `{"Authorization": f"Bearer {credentials.secret_value()}"}`
- `MuseVerifier`: `{"Authorization": f"Bearer {credentials.secret_value()}"}`

`_BaseProviderVerifier._classify_status` and `_validate_body` stay unchanged (429, 401/403, 5xx, non-2xx, empty/oversized/non-JSON/missing `data` list). `verifier_for_provider` extends the factory to four new branches; the command does not branch on `if provider`.

#### Edge Cases & Error Handling

- Each verifier sends exactly one `Authorization` header, no `x-api-key` or `anthropic-version` duplication.
- Body shape is the same `data` list guard the existing verifiers use; DeepSeek, xAI, Z.AI, and Meta all return OpenAI-style `{object:"list", data:[...]}` on the models endpoint.

### 6.5 Provider Resolver

**File(s):** `src/vidbyte_cli/lib/auth/provider_resolver.py`
**Type:** Modified

#### What it does

Env > keyring > file resolution with provider-namespaced env var lookup. No code change in algorithm, only the `PROVIDER_ENV_VARS` map grows.

#### Logic / Algorithm

1. Check `environment[PROVIDER_ENV_VARS[provider]]` - if present, `strip()`, bounds `1..4096`, `is_live_format`; if invalid -> `InvalidProviderEnvironmentKey(provider, var)`.
2. Else `store.keyring.read` -> `KEYRING`; else `store.file.read` -> `RESTRICTED_FILE`; else `None`.

No alias like `CLAUDE_API_KEY` for Claude or `ZHIPU_API_KEY` for GLM - one canonical var per provider. For GLM, `ZAI_API_KEY` is canonical (Z.AI international); document that `ZHIPU_API_KEY` is not read to avoid silent precedence widening.

### 6.6 Provider Store & Paths

**File(s):** `src/vidbyte_cli/lib/auth/provider_store.py`, `src/vidbyte_cli/lib/config/paths.py`
**Type:** No change (store already scopes by `provider`; paths already expose `provider_credentials_file()`).

#### What it does

`ProviderCredentialStore` keyring service `vidbyte-cli-provider` and `FileProviderStore` document `provider-credentials.json` already handle arbitrary `Provider` values. No schema change beyond new entries like `default@grok`.

### 6.7 Commands

**File(s):** `src/vidbyte_cli/commands/provider/login.py`, `logout.py`, `whoami.py`
**Type:** No change (already parameterized by `Provider` and `click.Choice([p.value for p in Provider])`; new enum members appear automatically).

### 6.8 ApplicationContext Wiring

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** No change (already exposes `provider_store()`, `provider_resolver()`, `provider_verifier(provider)` with lazy factories).

### 6.9 Failure Classes

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified only if a new distinct failure is needed; otherwise reuse existing provider failures.

All existing provider failures already include the provider name in their message (`f"The {provider} provider rejected the API key."`) so adding four providers does not need new classes. `ProviderKeyNotLiveFormat` already formats `f"The value is not a {provider} API key."` which covers `muse` (`LLM|`) and `deepseek` (`sk-`).

---

## 7. Data Model Changes

### 7.1 CLI-Local Provider Document

**Change type:** Additive entries in existing file.

Path: `{data_root}/provider-credentials.json` via `VidbytePaths.provider_credentials_file()`. Schema `schema_version:1` unchanged. New entries are `"{profile}@grok"`, `"{profile}@deepseek"`, `"{profile}@glm"`, `"{profile}@muse"` with `SecretStr` values. Existing `default@openai` and `default@claude` entries remain valid and untouched. No migration, no `clear_legacy`.

---

## 8. API Changes

No Vidbyte backend API changes.

Provider probes (not Vidbyte-controlled):

- `GET https://api.x.ai/v1/models` — header `Authorization: Bearer <key>` — expected `200 {object:"list", data:[{id,...}]}`. Ref: `docs.x.ai`.
- `GET https://api.deepseek.com/v1/models` — header `Authorization: Bearer <key>` — expected `200 {object:"list", data:[{id: "deepseek-v4-flash", object:"model"}]}`. Ref: `api-docs.deepseek.com/api/list-models`.
- `GET https://api.z.ai/api/paas/v4/models` — header `Authorization: Bearer <key>` — expected `200 {object:"list", data:[...]}` (OpenAI-compatible). Ref: `docs.z.ai/api-reference/introduction` (base `https://api.z.ai/api/paas/v4`), chat endpoint docs.
- `GET https://api.meta.ai/v1/models` — header `Authorization: Bearer <key>` — expected `200 {data:[{id,...}]}` / `{object:"list", data:[...]}`. Ref: `ai.developer.meta.com/docs/api-reference/models/list-models`.

Failure shapes are provider-specific; client classifies only by status/bounds/shape per §6.4.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/provider-byok-login-extended.md` | This design doc |
| MODIFY | `src/vidbyte_cli/types/provider.py` | 4 new enum members + env/probe/display/prefix maps |
| MODIFY | `src/vidbyte_cli/lib/auth/provider_credentials.py` | Extend `is_live_format` for deepseek/muse/grok/glm |
| MODIFY | `src/vidbyte_cli/lib/auth/provider_verifier.py` | 4 new `*_Verifier` classes + factory branches |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Only if a new failure class is needed; otherwise no change (failures already provider-parameterized) |
| MODIFY | `README.md` | Document 4 new provider choices in provider login help |
| MODIFY | `scripts/test-provider-byok-login.py` | Extend parameterized tests to cover 4 new providers |

Dependent but unchanged files (no edits): `src/vidbyte_cli/lib/auth/provider_resolver.py`, `src/vidbyte_cli/lib/auth/provider_store.py`, `src/vidbyte_cli/lib/config/paths.py`, `src/vidbyte_cli/lib/runtime/context.py`, `src/vidbyte_cli/commands/provider/*` (auto-extended via enum).

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|-------------------|---------|------|
| `httpx` | `>=0.27,<1` (exists) | Provider probes | No new dep; lazy import inside `verify` |
| `keyring` | `>=25.2` (exists) | Provider key storage | Reuses existing service, new provider keys only |
| `api.x.ai` | `GET /v1/models` | Grok probe | External; rate-limited |
| `api.deepseek.com` | `GET /v1/models` | DeepSeek probe | External; rate-limited |
| `api.z.ai` | `GET /api/paas/v4/models` | GLM probe | External; rate-limited; one canonical host |
| `api.meta.ai` | `GET /v1/models` | Muse probe | External; rate-limited |

---

## 11. Rollout & Deployment

- Additive only; `provider --help` remains side-effect free. Rollback is removing the four enum members and their verifier branches; the file stays inert.
- Executor PR will resolve keys via `ProviderResolver.resolve(profile, provider)` and inject as explicit client arg/env - no global `os.environ` mutation.
- No feature flag needed.

---

## 12. Open Questions

- [ ] GLM host: should `GLM` probe `https://open.bigmodel.cn/api/paas/v4/models` as a fallback when `api.z.ai` is unreachable, or strictly one canonical host? This doc chooses one canonical host to keep classification simple.
- [ ] Grok/GLM prefix: should they gain a loose prefix hint (e.g. `xai-` or hex check) to catch cross-provider paste errors, or stay prefix-free? This doc stays prefix-free because no stable prefix is documented.
- [ ] Env alias for GLM: should `ZHIPU_API_KEY` be read as an alias for `ZAI_API_KEY`? This doc says no to avoid silent precedence widening, but an alias could be added with a deprecation warning.

---

## 13. Testing Plan

Harness: extend `scripts/test-provider-byok-login.py` against loopback `http.server.ThreadingHTTPServer` (bound to `127.0.0.1:0`), injected `KeyringBackend` fake with controllable `priority`, temp `VidbytePaths` under `tmp_path`. Exercises real `httpx` transport; keyring fake to avoid OS dialog.

### Unit Tests — Provider Type Maps

- [Edge Case] `Provider("grok")` / `deepseek` / `glm` / `muse` coercion succeeds; `Provider("GROK")` fails (case-sensitive via `click.Choice`).
- [Hidden Assumption] Every `Provider` has an entry in `PROVIDER_ENV_VARS`, `PROVIDER_PROBE_URLS`, `PROVIDER_DISPLAY`, and `PROVIDER_KEY_PREFIXES` (including empty tuple for prefix-free providers).
- [Silent Failure] `--help` does not import `httpx` or touch `provider-credentials.json` (side-effect free registration).

### Unit Tests — ProviderCredentials.is_live_format

- [Edge Case] `muse` with `LLM|...` -> true; `muse` with `sk-...` -> `ProviderKeyNotLiveFormat` without network.
- [Edge Case] `deepseek` with `sk-abc` -> true; `deepseek` with `LLM|...` -> `ProviderKeyNotLiveFormat`.
- [Hidden Assumption] `grok` with any non-empty 1..4096 string like `xai-abc` or `opaque123` -> `is_live_format` true (no prefix filter).
- [Hidden Assumption] `glm` with any non-empty string -> `is_live_format` true.
- [Edge Case] Empty after trim -> `InvalidProviderApiKeyInput`.
- [Edge Case] 4097 chars -> `InvalidProviderApiKeyInput`.

### Unit Tests — Verifiers (parameterized over 4 new providers + existing 2)

- [Edge Case] 200 valid JSON `{object:"list", data:[{id,...}]}` or `{data:[{id,...}]}` -> `ProviderIdentity(verified=True)`.
- [Silent Failure] Each verifier sends exactly `Authorization: Bearer <key>` + `Accept: application/json` and no `x-api-key`/`anthropic-version` (unlike Claude). Assert for `grok`/`deepseek`/`glm`/`muse` individually.
- [Hidden Failure] Does not follow 302 to another origin - target server receives zero requests.
- [Hidden Failure] Transport timeout -> `ProviderApiUnreachable` not `ProviderCredentialsRejected`.
- [Edge Case] 401 -> `ProviderCredentialsRejected` exit 4, nothing stored.
- [Edge Case] 403 -> same as 401.
- [Edge Case] 429 with `Retry-After: 60` -> `ProviderRateLimited` hint carries `60`; without header -> no crash.
- [Edge Case] 200 `content-type: text/html` -> `ProviderApiProtocolError`.
- [Edge Case] Body `>1_048_576` or empty -> `ProviderApiProtocolError`.
- [Edge Case] 200 `{object:"list"}` missing `data` -> `ProviderApiProtocolError`.
- [Silent Failure] No response body quoted in any failure `message`/`description`.

### Integration Tests — Login through store (parameterized)

- [Hidden Assumption] Stores after 200 only - keyring contains `default@grok` etc. after accept.
- [Silent Failure] Writes nothing to keyring nor file on 401 for each new provider.
- [Silent Failure] Second failed login leaves existing stored key intact.
- [Hidden Failure] Sends exactly one probe per login (no retry).
- [Edge Case] `--allow-file-fallback` on headless host writes to `provider-credentials.json` with restricted permissions; keyring `priority < 1` triggers fallback path.
- [Hidden Assumption] `provider logout grok` clears only `default@grok`, not `default@openai` or `default@glm` (scoped clear).
- [Edge Case] `provider whoami muse` with no stored key -> `ProviderAuthenticationRequired` without a network call; with stored key -> one probe to `https://api.meta.ai/v1/models`.
- [Edge Case] Env var set-but-invalid (e.g. `MODEL_API_KEY=""` or `MODEL_API_KEY="sk-..."` wrong prefix for muse) -> `InvalidProviderEnvironmentKey` not silent fallthrough to keyring.

---

## 14. Alternatives Considered

### Alternative 1: One generic verifier with URL/header templates

- What: Store `PROVIDER_PROBE_URLS` + `PROVIDER_AUTH_HEADER="bearer"` template and use a single `GenericBearerVerifier`.
- Why rejected: Saves 4 small classes but loses the factory's closed extension point and makes a future non-Bearer provider (like a new Anthropic-style `x-api-key` variant) harder to add without reopening the generic path. Four 6-line classes are cheaper than a template engine.

### Alternative 2: Support both Z.AI hosts simultaneously

- What: Probe `api.z.ai` then fallback to `open.bigmodel.cn` when the first fails with transport error.
- Why rejected: Fallback doubles probe cost and blurs failure classification (transport vs auth). One canonical host is simpler; a user who needs the mainland host can set `ZAI_API_KEY` from that account - the key itself is the same shape and the same Bearer header works on either host.

### Alternative 3: Add env var aliases (`ZHIPU_API_KEY`, `X_AI_API_KEY`, `DEEPSEEK_KEY`)

- What: Read multiple env var names per provider with precedence.
- Why rejected: Widens secret precedence silently and makes `InvalidProviderEnvironmentKey` ambiguous about which var was wrong. One canonical var per provider (`XAI_API_KEY`, `DEEPSEEK_API_KEY`, `ZAI_API_KEY`, `MODEL_API_KEY`) matches each provider's own SDK/docs; alias can be added later if users request it.

### Alternative 4: Enforce `xai-` prefix for Grok

- What: Require Grok keys to start with `xai-` to catch cross-provider paste errors.
- Why rejected: No stable prefix is published in `docs.x.ai`; enforcing it would reject valid opaque keys and break rotation if xAI changes format. Bounds check alone is safer.

---

## 15. Rollout Risks

- Four external probes increase rate-limit surface but each login sends exactly one non-retried request; classify 429 as `ProviderRateLimited` with hint.
- GLM's OpenAPI YAML does not document `GET /models` at `api.z.ai`, but the OpenAI-compatible surface is expected to expose it like the other providers - verify against live endpoint before claiming success in the PR body, or note as a follow-up if the probe needs adjustment.
- Key prefix checks are intentionally strict for `muse` (`LLM|`) and `deepseek` (`sk-`) but intentionally loose for `grok`/`glm`; document this in the docstring so reviewers do not tighten them later without a docs change.
