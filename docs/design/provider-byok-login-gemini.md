# Design Doc: Provider BYOK Login - Gemini

**Status:** Draft
**Author:** Muse Spark
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

Add `vidbyte-cli provider login gemini` (and matching `logout`/`whoami`) as BYOK for Google Gemini, extending the provider BYOK surface that already covers `openai`, `claude`, `grok`, `deepseek`, `glm`, `muse`. Gemini is the old vet the user flagged - the longest-running frontier API. The change reuses the exact invariants from `provider-byok-login` and `provider-byok-login-extended`: hidden prompt or `--with-token` stdin, verify-before-persist, keyring-first with consent-gated `restricted_file`, `profile@provider` scoping, `env > keyring > file`. Only the probe string, header, and body shape differ.

---

## 2. Goals & Non-Goals

### Goals

- One new provider choice `gemini` under the existing `provider` group with `login`/`logout`/`whoami`, same two outcomes: accept (verified and stored) or reject (typed failure, nothing stored).
- Reuse invariants: no `--api-key` argv, `SecretStr`, verify before write, lazy `import httpx`, bounded I/O, `follow_redirects=False`, no secret echo.
- Probe matches official docs: `GET https://generativelanguage.googleapis.com/v1beta/models` with `x-goog-api-key: <key>` (canonical per `ai.google.dev/api`), also accepting the `?key=` query form is out of scope.
- Zero new deps; `httpx` and `keyring` already declared.

### Non-Goals

- Wiring the key into `RuntimeExecutor` - same boundary as prior provider docs. Executor will call `ProviderResolver.resolve()` later.
- Supporting Google Cloud Vertex AI auth (`gcloud` ADC, OAuth access token, `Authorization: Bearer` with `generativelanguage.googleapis.com` via `x-goog-user-project`) - BYOK is the API-key path only.
- Supporting `--api-key` argv or exposing the key in `whoami`.
- Backend Vidbyte routes.

---

## 3. Background & Context

- `provider-byok-login` (`1406fe5`) shipped `openai`/`claude` with `Provider` enum, `ProviderCredentials.is_live_format`, `ProviderVerifier` base (`src/vidbyte_cli/lib/auth/provider_verifier.py:42`), `ProviderStore`/`ProviderResolver`, and `provider` command group. `provider-byok-login-extended` added `grok`/`deepseek`/`glm`/`muse` on branch `feat/provider-byok-login-extended` (commit `0aa33b0`).
- Docs probed 2026-09-05 for Gemini:
  - Auth: `x-goog-api-key: $GEMINI_API_KEY` (preferred) per `ai.google.dev/api` ("All requests to the Gemini API must include a `x-goog-api-key` header"), also `ai.google.dev/gemini-api/docs/api-key` ("Set `GEMINI_API_KEY` or `GOOGLE_API_KEY`; `GOOGLE_API_KEY` takes precedence"). Keys look like `AIza...` (39 chars), prefix `AIza`.
  - Probe: `GET https://generativelanguage.googleapis.com/v1beta/models` with `-H "x-goog-api-key: $GEMINI_API_KEY"` returns `{"models": [{"name":"models/gemini-3-flash-preview", ...}]}`. Ref: `ai.google.dev/api/models` (`GET /v1beta/models`), `ai.google.dev/gemini-api/docs/models` (`GET`/`list`). Body shape differs from OpenAI-style `{object:"list", data:[...]}` — Gemini uses `{"models":[...]}`.
- Repo is thin transport (`AGENTS.md` output contract, `field-guide/vidbyte-cli/typed-failures.md` one subclass per failure). `ProviderVerifier` owns its own `httpx.Client` with lazy import to keep `--help` fast (`login-key-verification.md` NFR-1: `httpx` adds ~0.14s if imported at module scope).
- Keyring service stays `vidbyte-cli-provider`, scoping `profile@provider`.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli provider login gemini` MUST exist alongside the six existing choices, accepting hidden prompt or `--with-token` stdin, no `--api-key` option. Choices stay case-sensitive via `click.Choice`.
2. Input MUST be bounded 1..4096 chars after `strip()`, rejected as `InvalidProviderApiKeyInput` otherwise, before any network call.
3. Input format MUST be checked via `ProviderCredentials.is_live_format(Provider.GEMINI, value)` — `value.startswith("AIza")` is required. Wrong prefix -> `ProviderKeyNotLiveFormat` without a network call. `is_live_format` MUST NOT be a Pydantic validator so a stored non-matching key remains removable.
4. Verification MUST probe `GET https://generativelanguage.googleapis.com/v1beta/models` with header `x-goog-api-key: <key>` and `Accept: application/json`, `follow_redirects=False`, timeout 15.0s. No `Authorization: Bearer` for Gemini.
5. Verification MUST NOT retry and MUST NOT echo key or body. Classification identical to other providers: 401/403 -> `ProviderCredentialsRejected` (exit 4), 429 -> `ProviderRateLimited` with `Retry-After` hint, 5xx/transport -> `ProviderApiUnreachable` (retryable), 400/404/409/422 and other non-2xx -> `ProviderRequestRejected`, empty/oversized/non-JSON/missing `models` list -> `ProviderApiProtocolError`.
6. On 2xx with valid JSON `models` list: store via `ProviderCredentialStore.write(profile, GEMINI)` keyring-first, consent-gated file fallback. Emit `kind="provider.login"` with `profile`, `provider`, `storage`.
7. On any failure: MUST NOT write, MUST NOT clear any existing stored key for any provider.
8. `provider logout gemini` MUST clear keyring + file for `profile@gemini` only; already-logged-out succeeds.
9. `provider whoami gemini` MUST resolve via `ProviderResolver` (env > keyring > file) without a network call when no credential exists; if found, re-probe and emit `kind="provider.whoami"` with `provider`, `profile`, `verified`, `credential_source`. If none -> `ProviderAuthenticationRequired`.
10. `--help`/`--version` MUST NOT touch keyring, files, or network; factories stay lazy in `lib/runtime/context.py`.
11. Failures remain typed `CliError` subclasses in `lib/errors/failures.py` - reuse existing provider failures (`ProviderKeyNotLiveFormat` for prefix, `ProviderCredentialsRejected`, etc.) which already include provider name. No new class needed.
12. Env var precedence: `GEMINI_API_KEY` is canonical; `GOOGLE_API_KEY` is a fallback alias read with lower precedence? To match Google docs ("`GOOGLE_API_KEY` takes precedence" when both set), resolver checks `GOOGLE_API_KEY` first, then `GEMINI_API_KEY`. Set-but-invalid (empty/oversized/wrong prefix) MUST raise `InvalidProviderEnvironmentKey(provider, var)` not fall through. Document the precedence.

### Non-Functional Requirements

- Startup: `import httpx` inside `verify` only.
- Bounded I/O: `+1` over-read on stdin, 1 MiB cap on probe response (`_MAX_RESPONSE_BYTES=1_048_576`).
- Secret hygiene: `SecretStr`, `secret_value()` unwrapped only where header is built. `description`/`trace` static, never echo bodies.

---

## 5. High-Level Design

No new command surface beyond enum expansion. The `provider` group already owns `login`/`logout`/`whoami` parameterized by `Provider`; adding `GEMINI` extends `click.Choice` automatically.

```
vidbyte-cli provider login gemini [--with-token][--allow-file-fallback]
        | -> ProviderCredentialInput.read(...)  # bounds + is_live_format(GEMINI -> AIza)
        | -> verifier_for_provider(GEMINI).verify(credentials)
        |       -> GeminiVerifier (GET https://generativelanguage.googleapis.com/v1beta/models, x-goog-api-key)
        | -> ProviderCredentialStore.write(profile, gemini)
```

Resolver: env `GEMINI_API_KEY` (`GOOGLE_API_KEY` fallback) > keyring > file, same `vidbyte-cli-provider` service + `provider-credentials.json` document (`default@gemini`).

```
[provider whoami gemini] -> ProviderResolver.resolve(profile, gemini) -> if found: GeminiVerifier.verify() -> OutputDocument kind="provider.whoami"
```

---

## 6. Detailed Design

### 6.1 Provider Types

**File(s):** `src/vidbyte_cli/types/provider.py`
**Type:** Modified

#### What it does

Closed enum + typed constant maps. No HTTP, no storage.

#### Interface / API

```python
class Provider(StrEnum):
    OPENAI = "openai"
    CLAUDE = "claude"
    GROK = "grok"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MUSE = "muse"
    GEMINI = "gemini"


PROVIDER_KEY_PREFIXES: dict[Provider, tuple[str, ...]] = {
    OPENAI: ("sk-",),
    CLAUDE: ("sk-ant-",),
    GROK: (),
    DEEPSEEK: ("sk-",),
    GLM: (),
    MUSE: ("LLM|",),
    GEMINI: ("AIza",),
}
PROVIDER_ENV_VARS: dict[Provider, str] = {
    OPENAI: "OPENAI_API_KEY",
    CLAUDE: "ANTHROPIC_API_KEY",
    GROK: "XAI_API_KEY",
    DEEPSEEK: "DEEPSEEK_API_KEY",
    GLM: "ZAI_API_KEY",
    MUSE: "MODEL_API_KEY",
    GEMINI: "GEMINI_API_KEY",
}
PROVIDER_PROBE_URLS: dict[Provider, str] = {
    OPENAI: "https://api.openai.com/v1/models",
    CLAUDE: "https://api.anthropic.com/v1/models",
    GROK: "https://api.x.ai/v1/models",
    DEEPSEEK: "https://api.deepseek.com/v1/models",
    GLM: "https://api.z.ai/api/paas/v4/models",
    MUSE: "https://api.meta.ai/v1/models",
    GEMINI: "https://generativelanguage.googleapis.com/v1beta/models",
}
# Env precedence for Gemini needs a list; single canonical entry stays here and resolver handles alias.
GEMINI_ENV_FALLBACK = "GOOGLE_API_KEY"
```

#### Edge Cases & Error Handling

- `Provider("gemini")` case-sensitive via `click.Choice`.

### 6.2 Provider Credential Model

**File(s):** `src/vidbyte_cli/lib/auth/provider_credentials.py`
**Type:** Modified

#### What it does

Adds `AIza` prefix gate for `GEMINI`; `GROK`/`GLM` stay opaque.

#### Interface / API

```python
class ProviderCredentials(BaseModel):
    @classmethod def is_live_format(cls, provider: Provider, value: str) -> bool: ...
```

#### Logic / Algorithm

- `GEMINI` -> `value.startswith("AIza")`
- `CLAUDE` -> `sk-ant-`, `OPENAI`/`DEEPSEEK` -> `sk-` not `sk-ant-`, `MUSE` -> `LLM|`, `GROK`/`GLM` -> any non-empty, fallback to prefix tuple.

#### Edge Cases & Error Handling

- `is_live_format` stays outside Pydantic validator so wrong-prefix stored keys remain removable.

### 6.3 Provider Input

**File(s):** `src/vidbyte_cli/lib/auth/provider_input.py`
**Type:** No structural change (already parameterized).

### 6.4 Provider Verification

**File(s):** `src/vidbyte_cli/lib/auth/provider_verifier.py`
**Type:** Modified

#### What it does

Adds `GeminiVerifier` with `x-goog-api-key` header and Gemini-specific body validation (`models` list instead of `data`).

#### Interface / API

```python
class GeminiVerifier(_BaseProviderVerifier):
    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity: ...
    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]: ...


def verifier_for_provider(provider: Provider) -> ProviderVerifier: ...
```

#### Logic / Algorithm

- `GeminiVerifier._headers()` -> `{"x-goog-api-key": credentials.secret_value()}`
- `verify()` -> `self._probe(credentials, timeout_seconds=15.0)` then `ProviderIdentity(provider=GEMINI)`.
- Body validation: override `_validate_body` for Gemini to accept either `data` list (OpenAI style) or `models` list (Gemini style). Simplest: base `_validate_body` accepts `payload.get("data")` or `payload.get("models")` is a list. That keeps one shared validator for all seven providers and matches Gemini's `{"models": [{"name":"models/gemini-..."}]}` shape, while still accepting OpenAI-style for others. Alternative is to override `_validate_body` in `GeminiVerifier` only; shared accept is simpler and documented.

`_probe` builds `{"Accept":"application/json", **_headers}` and `client.get(PROVIDER_PROBE_URLS[provider])` with `follow_redirects=False`. `_classify_status` unchanged.

Factory adds `if provider == Provider.GEMINI: return GeminiVerifier()`.

#### Edge Cases & Error Handling

- Sends exactly `x-goog-api-key` + `Accept`, no `Authorization: Bearer` or `x-api-key`/`anthropic-version`.
- Never echo body; `_validate_body` bounds/payload checks before any logging.

### 6.5 Provider Resolver

**File(s):** `src/vidbyte_cli/lib/auth/provider_resolver.py`
**Type:** Modified

#### What it does

Env > keyring > file with provider-namespaced lookup; adds `GOOGLE_API_KEY` fallback for `GEMINI`.

#### Interface / API

```python
class ProviderResolver:
    def resolve(self, profile: str, provider: Provider) -> ResolvedProviderCredential | None: ...
```

#### Logic / Algorithm

For `provider == GEMINI`:
1. Check `environment["GOOGLE_API_KEY"]` first (per Google docs precedence), then `environment["GEMINI_API_KEY"]` if the first is absent. If either is present, `strip()`, bounds 1..4096, `is_live_format(GEMINI, value)` — if invalid -> `InvalidProviderEnvironmentKey` with that var name.
2. Else keyring/file as usual.

For other providers: existing single-var path via `PROVIDER_ENV_VARS`.

#### Edge Cases & Error Handling

- When both `GOOGLE_API_KEY` and `GEMINI_API_KEY` are set, `GOOGLE_API_KEY` wins (matches client library precedence). If the winning var is invalid, raise rather than falling through to the other var — set-but-invalid is an error, not a silent miss.

### 6.6 Store & Paths

**File(s):** `src/vidbyte_cli/lib/auth/provider_store.py`, `src/vidbyte_cli/lib/config/paths.py`
**Type:** No change (already scopes by `provider`; file handles arbitrary `Provider`).

### 6.7 Commands

**File(s):** `src/vidbyte_cli/commands/provider/login.py`
**Type:** Modified (help string)

Help text updates from `(openai, claude, grok, deepseek, glm, muse)` to include `gemini`.

`logout.py`/`whoami.py` need no change - parameterized.

### 6.8 ApplicationContext

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** No change (lazy factories already present).

### 6.9 Failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** No change (existing provider failures are provider-parameterized and cover prefix/401/429/etc.).

---

## 7. Data Model Changes

### 7.1 CLI-Local Provider Document

**Change type:** Additive entry.

Path `{data_root}/provider-credentials.json` via `VidbytePaths.provider_credentials_file()`. Schema `schema_version:1` unchanged. New entry `"{profile}@gemini"` with `SecretStr`. Existing entries untouched. No migration.

---

## 8. API Changes

No Vidbyte backend API changes.

Provider probe:

- `GET https://generativelanguage.googleapis.com/v1beta/models` — header `x-goog-api-key: <key>` — expected `200 {"models":[{"name":"models/gemini-3-flash-preview", "displayName":"Gemini 3 Flash", ...}]}`. Ref: `ai.google.dev/api`, `ai.google.dev/gemini-api/docs/models` (list), `ai.google.dev/gemini-api/docs/api-key` (x-goog-api-key auth).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/provider-byok-login-gemini.md` | This design doc |
| MODIFY | `src/vidbyte_cli/types/provider.py` | Add GEMINI enum member + maps |
| MODIFY | `src/vidbyte_cli/lib/auth/provider_credentials.py` | Add `AIza` prefix gate for GEMINI |
| MODIFY | `src/vidbyte_cli/lib/auth/provider_verifier.py` | Add `GeminiVerifier` + factory branch + `models` accept in `_validate_body` |
| MODIFY | `src/vidbyte_cli/lib/auth/provider_resolver.py` | Add `GOOGLE_API_KEY` fallback for GEMINI env precedence |
| MODIFY | `src/vidbyte_cli/commands/provider/login.py` | Update help text to include gemini |
| MODIFY | `scripts/test-provider-byok-login-extended.py` | Extend parameterized tests to cover gemini (prefix, x-goog-api-key header, models body, env alias) |

Unchanged: `lib/auth/provider_store.py`, `lib/config/paths.py`, `lib/runtime/context.py`, `commands/provider/logout.py`, `commands/provider/whoami.py`.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|-------------------|---------|------|
| `httpx` | `>=0.27,<1` (exists) | Gemini probe | No new dep; lazy import |
| `keyring` | `>=25.2` (exists) | Storage | Reuses `vidbyte-cli-provider` service |
| `generativelanguage.googleapis.com` | `GET /v1beta/models` | Gemini probe | External; rate-limited; `x-goog-api-key` header (not Bearer) |

---

## 11. Rollout & Deployment

- Additive only; `provider --help` side-effect free. Rollback by removing `GEMINI` enum + verifier branch; file stays inert.
- Executor will resolve via `ProviderResolver.resolve(profile, GEMINI)` and pass as `genai.Client(api_key=secret)` or `GEMINI_API_KEY` env.
- No feature flag.

---

## 12. Open Questions

- [ ] Should `GOOGLE_API_KEY` remain a silent alias or be the canonical var? This doc keeps `GEMINI_API_KEY` canonical with `GOOGLE_API_KEY` as precedence fallback to match `ai.google.dev` docs.
- [ ] Should the body validator accept both `data` and `models` for all providers, or only override for Gemini? This doc accepts both in the shared validator to keep one code path; a strict Gemini-only override is the alternative.

---

## 13. Testing Plan

Harness: extend `scripts/test-provider-byok-login-extended.py` against loopback `ThreadingHTTPServer` at `127.0.0.1:0`, fake `KeyringBackend`, temp `VidbytePaths`. Real `httpx` transport.

### Unit Tests — Provider Type Maps

- [Edge Case] `Provider("gemini")` coercion succeeds; `Provider("GEMINI")` fails (case-sensitive).
- [Hidden Assumption] Every `Provider` has entries in `PROVIDER_ENV_VARS`, `PROVIDER_PROBE_URLS`, `PROVIDER_DISPLAY`, `PROVIDER_KEY_PREFIXES` (including `GEMINI: ("AIza",)`).
- [Silent Failure] `--help` does not import `httpx` or touch file.

### Unit Tests — ProviderCredentials.is_live_format (Gemini)

- [Edge Case] `gemini` with `AIza...` -> true; `gemini` with `sk-...` -> `ProviderKeyNotLiveFormat` without network; `gemini` with empty -> `InvalidProviderApiKeyInput`.
- [Hidden Assumption] `gemini` with `AIza` prefix alone (`"AIza"`) is considered live format (prefix check is `startswith`) - intentional, bounds check still applies.
- [Silent Failure] `extra="forbid"` still rejects stray fields.

### Unit Tests — Verifiers (Gemini)

- [Edge Case] 200 valid Gemini body `{"models":[{"name":"models/gemini-2.0-flash"}]}` -> `ProviderIdentity(verified=True)`.
- [Silent Failure] Gemini sends exactly `x-goog-api-key: <key>` + `Accept: application/json` and no `Authorization: Bearer` or `x-api-key`/`anthropic-version`.
- [Hidden Failure] Transport timeout -> `ProviderApiUnreachable` not `ProviderCredentialsRejected`.
- [Edge Case] 401/403 -> `ProviderCredentialsRejected` exit 4, nothing stored; 429 with `Retry-After: 60` surfaces hint; 500 -> `ProviderApiUnreachable`.
- [Edge Case] 200 `{"models": []}` (empty list) is accepted (list check passes); 200 `{"models": "nope"}` or missing `models`/`data` -> `ProviderApiProtocolError`.
- [Edge Case] Oversized body >1 MiB -> `ProviderApiProtocolError`.

### Integration Tests — Login through store (Gemini)

- [Hidden Assumption] Stores after 200 only - keyring contains `default@gemini`.
- [Silent Failure] Writes nothing on 401/500; second failed login leaves prior key intact; exactly one probe per login.
- [Edge Case] `--allow-file-fallback` on headless host writes to `provider-credentials.json` with restricted permissions; no-consent writes nothing.

### Integration Tests — Resolver Precedence (Gemini)

- [Edge Case] `GOOGLE_API_KEY` outranks `GEMINI_API_KEY` when both set; both unset -> keyring/file.
- [Hidden Assumption] Set-but-invalid `GOOGLE_API_KEY=""` -> `InvalidProviderEnvironmentKey` (does not fall through to `GEMINI_API_KEY` or keyring).
- [Edge Case] Valid `GEMINI_API_KEY` with correct `AIza` prefix resolves as `environment`.

### Integration Tests — Whoami/Logout Scoping

- [Edge Case] `provider whoami gemini` with no key -> `ProviderAuthenticationRequired` without probe; with key -> one probe to `generativelanguage.googleapis.com`.
- [Hidden Assumption] `provider logout gemini` clears only `default@gemini`, not `default@openai`.

---

## 14. Alternatives Considered

### Alternative 1: Use `Authorization: Bearer` for Gemini

- What: Probe with `Authorization: Bearer $GEMINI_API_KEY` like OpenAI.
- Why rejected: Gemini docs mandate `x-goog-api-key` header (or `?key=` query); `Authorization: Bearer` is for OAuth access tokens via Vertex AI, not the API-key path this CLI implements. Using Bearer would 401 all API-key logins.

### Alternative 2: Accept `?key=` query param instead of header

- What: Append API key as URL query `?key=<value>`.
- Why rejected: Keys in URLs leak to logs/proxies/history; header is the documented secure form and the only one this doc supports. Query form is intentionally not implemented.

### Alternative 3: Separate Gemini body validator class

- What: Override `_validate_body` only in `GeminiVerifier` to check `models` list, keeping base validator strictly `data` list.
- Why rejected: Shared validator accepting both `data` or `models` is one place to change and handles future providers that use either shape (Cohere uses `models` too). A strict per-verifier split would duplicate bounds/JSON parsing.

---

## 15. Rollout Risks

- Gemini's `models` shape vs OpenAI's `data` shape is the only protocol divergence; shared validator accepting both prevents a regression where a correct 200 is rejected as protocol error.
- Google may return 400 with `"API key not valid"` vs 401/403 - map 400 to `ProviderRequestRejected` (existing classification) so the user sees "rejected the request" rather than a protocol error; 401/403 still map to `ProviderCredentialsRejected` for the auth-specific hint.

