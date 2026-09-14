# Design Doc: Connection Login Actionable Failures

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-14
**Last Updated:** 2026-09-14

---

## 1. Overview

PR #49 (`feat/context-provider-connections`) adds GitHub device-flow, Slack PKCE, and Google Drive installed-app logins, and it already funnels every login failure through typed `CliError` subclasses rendered for both humans and agents. The gap is that most provider-denied cases collapse into one generic `CONNECTION_OAUTH_FAILED` message ("retry and approve before expiry"), so an agent reading stderr cannot tell denial from expiry, bad client config from bad scopes, rate-limit from outage, or loopback-blocked from user-abandoned. This change adds one semantic failure class per actionable login failure mode, each with a message, description, trace, and hint that names the exact fix and next command, without ever echoing secrets, codes, or provider bodies.

---

## 2. Goals & Non-Goals

### Goals

- Give every common `connections login` failure its own `CliError` subclass with an agent-actionable hint.
- Cover GitHub device flow, Slack PKCE (`oauth.v2.access` + `auth.test`), Google installed-app PKCE, plus shared loopback, browser, network, keyring, and CLI-usage modes.
- Preserve existing stable `CliErrorCode` strings; new classes reuse existing codes (no code-string renames).
- Keep `cause` private and never serialize secrets, authorization codes, PKCE verifiers, tokens, or provider bodies.
- Keep stdout-is-results-only and stderr error envelope (`code`, `message`, `description`, `trace`, `file_path`, `hint`) unchanged.
- Add offline verification script covering every new mapping.

### Non-Goals

- Do not change successful login, token storage shape, metadata schema, refresh timing, or read/logout behavior.
- Do not add new provider scopes, new resources, new commands, or new CLI flags.
- Do not add live-network tests; all verification uses loopback fakes and stubbed `OAuthHttpClient`.
- Do not rename or remove any shipped `CliErrorCode` or `ExitCode`.
- Do not echo provider `error_description`, `error_uri`, or response bodies into agent output.

---

## 3. Background & Context

- PR #49 branch is `feat/context-provider-connections` targeting `main` in `cerredz/Vidbyte-cli`; PR body lists 37/37 connection checks and 51/51 surface checks passing.
- Current taxonomy lives in `src/vidbyte_cli/lib/errors/failures.py` with codes in `src/vidbyte_cli/lib/errors/codes.py`; rendering lives in `src/vidbyte_cli/lib/output/manager.py`; classification lives in `src/vidbyte_cli/lib/errors/handler.py`.
- Current adapters: `lib/connections/providers/github.py` (device poll handles only `authorization_pending` / `slow_down`), `slack.py` (`_require_ok` handles `missing_scope`, `invalid_auth`/`token_revoked`/`account_inactive`, `channel_not_found`/`not_in_channel`/`is_archived`), `google_drive.py` (`_validate_callback` checks state + generic `error`), shared `lib/connections/oauth.py` (`_classify_status` maps 429/401-403/404-resource/5xx/3xx).
- Field-guide constraints apply: `typed-failures.md` (one class per failure, `description` 3-4 sentences with what was/wasn't done + retry guidance, `trace` is semantic path not stack dump, no bare `CliError(...)`, no module-level error factory functions, no hand-written `file_path`), `agent-driven-command-surfaces.md` (no new config-file flags), `implementation-restraint.md` (small PR, sparse comments, class-first only where it earns its place).
- `AGENTS.md` output contract is the reason this work matters: agents invoke the default human format, so the hint text itself is the repair API.

---

## 4. Requirements

### Functional Requirements

1. GitHub device polling must map `access_denied` to a denial failure telling the agent the user cancelled and to start a fresh login.
2. GitHub device polling must map `expired_token` to an expiry failure telling the agent the device code died and to start a fresh login for a new code.
3. GitHub device polling must map `incorrect_device_code`, `incorrect_client_credentials`, and `unsupported_grant_type` to a client-config failure naming `VIDBYTE_GITHUB_CLIENT_ID` (and secret where relevant) as the fix.
4. GitHub token exchange returning HTTP 400 with an `error` field must not surface as "approve before expiry"; it must surface the denied/expired/client failure above.
5. Slack callback `error=access_denied` must map to a Slack denial failure (user or admin denied workspace install), distinct from state mismatch.
6. Slack `oauth.v2.access` and refresh responses with `ok:false` + `error=invalid_code` (expired/used code, PKCE verifier mismatch, redirect mismatch) must map to an invalid-grant failure telling the agent to start one fresh login and use the newest browser URL.
7. Slack `ok:false` + `error=ratelimited` / `rate_limited` / `ratelimited` variants must map to retryable `CONNECTION_RATE_LIMITED` with wait-and-retry guidance, not generic OAuth failure.
8. Slack refresh with `ok:false` + `error=invalid_client`, `invalid_code`, `bad_redirect_uri`, `invalid_refresh_token`, or unknown refresh errors must map to re-authentication or client-config failures, never generic OAuth failure.
9. Slack `invalid_client` / `bad_redirect_uri` on login must map to a client-config failure naming `VIDBYTE_SLACK_CLIENT_ID` and localhost redirect.
10. Google callback `error=access_denied` must map to a Google denial failure (account picker Cancel / consent denied), distinct from state forgery.
11. Google token exchange `invalid_grant` (expired/reused code, PKCE mismatch, redirect mismatch) must map to an invalid-grant failure with fresh-login guidance.
12. Google token exchange `invalid_client` / `unauthorized_client` must map to a client-config failure naming the `--client-secrets` / `VIDBYTE_GOOGLE_CLIENT_SECRETS` JSON as the fix.
13. Google token exchange `invalid_scope` must map to a scope failure telling the agent which requested scope string was rejected and to retry with `drive.readonly` default.
14. Google Drive read 403 with insufficient-permission semantics must map to `CONNECTION_SCOPE_INSUFFICIENT`, not `CONNECTION_AUTH_REQUIRED`, when the token is valid but lacks `drive.readonly`.
15. Loopback bind `OSError` in `OAuthCallbackServer.__init__` must map to a loopback-unavailable failure (port/firewall/permission), distinct from user timeout.
16. `OAuthCallbackServer.wait` timeout must map to a callback-timeout failure (browser never completed approval), distinct from bind failure, with "start fresh login, complete approval within timeout" guidance.
17. Keyring write/read-back failure after a verified OAuth grant must map to a save-failed failure stating the provider grant succeeded but nothing was persisted, with unlock/retry guidance.
18. Every new failure message, description, and hint must contain no secret, code, verifier, token, email, file ID, or provider body; provider error strings are matched in code but never interpolated into output.
19. Existing codes, exit statuses, and `retryable` flags keep their semantics: rate-limit and API-unavailable stay retryable; denial/expiry/client-config/state stay non-retryable.

### Non-Functional Requirements

- Performance: no extra network round-trips; classification is pure string matching on already-fetched payloads.
- Security: static prose only; `cause` carries the raw exception privately; debug traces show frames only per `handler.py`.
- Observability: human stderr and JSON error documents carry identical `code`/`description`/`trace`/`hint`; `file_path` stays auto-derived.
- Reliability: login must still persist nothing on any failure path (existing requirement 5 of base doc preserved).
- Lint: `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy src`, `python lint/run.py`, `python scripts/run_ci.py` must pass.

---

## 5. High-Level Design

Add narrow semantic subclasses in `lib/errors/failures.py` reusing shipped `CliErrorCode` values, then call them from the three provider adapters and the shared OAuth callback server. No new codes, no new commands, no storage changes.

Data flow stays identical: `[click login] -> [ConnectionManager.login] -> [adapter.login] -> [OAuthHttpClient / OAuthCallbackServer] -> [verify] -> [store.save]`. The only change is at each decision point where code today raises generic `ConnectionOAuthFailed`: match the provider's documented `error` string first and raise the specific class with a fix-up hint.

```text
[Click login] -> [ConnectionManager] -> [GitHub | Slack | Drive adapter]
      |                     |                        |
      v                     v                        v
[typed denial/expiry/grant/scope/rate-limit/loopback/keyring failure]
      |
      v
[ErrorHandler.handle] -> [OutputManager.error to stderr, human + JSON]
```

Key decisions: reuse codes so automation branching on `CONNECTION_OAUTH_FAILED` / `CONNECTION_RATE_LIMITED` / `CONNECTION_REAUTH_REQUIRED` keeps working while prose becomes specific; match Slack `ratelimited` inside `_require_ok` because Slack returns HTTP 200 where `_classify_status` cannot see it; split Google 403 handling inside the Drive adapter (not the shared client) because only Drive knows insufficient-permission means re-scope.

---

## 6. Detailed Design

### 6.1 GitHub denial, expiry, and client failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/lib/connections/providers/github.py`
**Type:** Modified

#### What it does

Gives the device-poll loop three actionable outcomes instead of one generic failure.

#### Interface / API

```python
class GitHubAccessDenied(CliError):
    def __init__(self) -> None: ...


class GitHubDeviceCodeExpired(CliError):
    def __init__(self) -> None: ...


class GitHubClientInvalid(CliError):
    def __init__(self, detail: str) -> None: ...
```

#### Logic / Algorithm

1. In the poll loop, read `token_payload.get("error")` into `outcome`.
2. If `outcome == "access_denied"` raise `GitHubAccessDenied` (code `CONNECTION_OAUTH_FAILED`, exit `AUTHENTICATION`, non-retryable; hint: user cancelled, start fresh `connections login github`, complete approval).
3. If `outcome == "expired_token"` raise `GitHubDeviceCodeExpired` (same code/exit; hint: code died after ~15 min, start fresh login for a new user code).
4. If `outcome in {"incorrect_device_code", "incorrect_client_credentials", "unsupported_grant_type"}` raise `GitHubClientInvalid` (code `CONNECTION_CONFIGURATION_INVALID`, exit `USAGE`; hint: check `VIDBYTE_GITHUB_CLIENT_ID`, do not reuse old device codes).
5. Keep `authorization_pending` / `slow_down` polling unchanged; keep final deadline timeout as `ConnectionOAuthFailed` with timeout cause.
6. Keep `refresh` mapping `error` -> `ConnectionReauthenticationRequired` unchanged.

#### Edge Cases & Error Handling

- Unknown non-empty `error` strings still raise generic `ConnectionOAuthFailed` so new GitHub strings fail closed.
- Empty-string `error` is treated as absent (some payloads include `"error": ""`).
- No provider string is interpolated into message/hint; matching is code-only.

### 6.2 Slack callback denial, invalid grant, rate limit, refresh mapping

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/lib/connections/providers/slack.py`
**Type:** Modified

#### What it does

Splits Slack's `ok:false` envelope and callback denial into agent-fixable failures.

#### Interface / API

```python
class SlackAccessDenied(CliError):
    def __init__(self) -> None: ...


class SlackInvalidGrant(CliError):
    def __init__(self) -> None: ...


class SlackClientInvalid(CliError):
    def __init__(self) -> None: ...
```

#### Logic / Algorithm

1. In `_validate_callback`, if `query.get("error") == "access_denied"` raise `SlackAccessDenied` (`CONNECTION_OAUTH_FAILED`; hint: user/admin denied, re-run login, approve workspace user scopes, contact admin if app is restricted); other non-empty `error` still raises generic `ConnectionOAuthFailed`.
2. In `_require_ok`, before the generic fallthrough: if `error in {"ratelimited", "rate_limited", "ratelimited_error"}` raise `ConnectionRateLimited("slack")` (existing class, retryable); if `error in {"invalid_code", "bad_redirect_uri_code", "code_expired"}` raise `SlackInvalidGrant` (`CONNECTION_OAUTH_FAILED`; hint: code single-use and short-lived, PKCE/redirect must match, start exactly one fresh login); if `error in {"invalid_client", "bad_redirect_uri", "invalid_redirect_uri"}` raise `SlackClientInvalid` (`CONNECTION_CONFIGURATION_INVALID`; hint: check `VIDBYTE_SLACK_CLIENT_ID`, localhost redirect, PKCE-enabled public app).
3. In `refresh`, wrap `_require_ok` outcome: `invalid_client` -> `SlackClientInvalid`; any other refresh `ok:false` (including `invalid_code`, `invalid_refresh_token`) -> `ConnectionReauthenticationRequired("slack")` so the agent runs login again instead of retrying refresh.
4. Reuse existing `ConnectionRateLimited` for the Slack 200-envelope case; do not invent a second rate-limit code.

#### Edge Cases & Error Handling

- `error` missing or `ok is True` proceeds unchanged.
- Unknown `error` strings fall through to generic `ConnectionOAuthFailed` (fail closed, no body echo).
- `missing_scope` / `invalid_auth` / channel mappings keep their existing precedence above the new branches.

### 6.3 Google denial, invalid grant, client, scope, and Drive 403 split

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/lib/connections/providers/google_drive.py`
**Type:** Modified

#### What it does

Makes Google's consent, code-exchange, and scope failures each explain their own fix.

#### Interface / API

```python
class GoogleAccessDenied(CliError):
    def __init__(self) -> None: ...


class GoogleInvalidGrant(CliError):
    def __init__(self) -> None: ...


class GoogleClientInvalid(CliError):
    def __init__(self) -> None: ...


class GoogleScopeInvalid(CliError):
    def __init__(self) -> None: ...
```

#### Logic / Algorithm

1. In `_validate_callback`, map `error=access_denied` to `GoogleAccessDenied` (`CONNECTION_OAUTH_FAILED`; hint: Cancel/deny in account picker, re-run login, select account, click Allow for readonly scope); other errors stay generic.
2. Add `_raise_for_token_error(payload)` called at the top of `_token_from_payload` and in `refresh`: read `payload.get("error")`; `invalid_grant` -> `GoogleInvalidGrant` (fresh login, single-use code, PKCE + redirect must match the authorizing request); `invalid_client`/`unauthorized_client` -> `GoogleClientInvalid` (`CONNECTION_CONFIGURATION_INVALID`; hint: `--client-secrets` / `VIDBYTE_GOOGLE_CLIENT_SECRETS` JSON, installed-app type, token URI must be the Google default); `invalid_scope` -> `GoogleScopeInvalid` (`CONNECTION_SCOPE_INSUFFICIENT`; hint: retry with default `drive.readonly`, do not request Gmail/Calendar scopes here).
3. In `read`, catch `ConnectionAuthenticationRequired` from the metadata GET and re-probe: if the token verifies via `verify()` then the 403 was scope/permission, raise `ConnectionScopeInsufficient("google-drive")` with re-login-with-scope hint; if verify also fails, let the original auth failure stand.
4. Keep `GoogleClientConfig.from_file` raising `ConnectionConfigurationInvalid` for malformed JSON; extend its `trace` to enumerate causes (oversized, no `installed` key, missing client ID, untrusted endpoint) without quoting file contents.

#### Edge Cases & Error Handling

- Token payloads without `error` proceed to existing `_text("access_token")` validation.
- `error_description` is never rendered; matching uses `error` code only.
- Drive export MIME gaps (Forms, Drawings, Sites) raise existing `ConnectionResourceUnavailable` with a hint naming the three supported export kinds.

### 6.4 Shared loopback, timeout, browser, and keyring-save failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/lib/connections/oauth.py`, `src/vidbyte_cli/lib/connections/manager.py`
**Type:** Modified

#### What it does

Separates "could not listen" from "user never finished" from "grant succeeded but save failed".

#### Interface / API

```python
class ConnectionLoopbackUnavailable(CliError):
    def __init__(self, provider: str) -> None: ...


class ConnectionCallbackTimeout(CliError):
    def __init__(self, provider: str) -> None: ...


class ConnectionSaveFailed(CliError):
    def __init__(self, provider: str) -> None: ...
```

#### Logic / Algorithm

1. `OAuthCallbackServer.__init__` `OSError` raises `ConnectionLoopbackUnavailable(provider)` (code `CONNECTION_API_UNAVAILABLE`, retryable False; hint: localhost blocked, firewall, permission, close conflicting listener, retry; GitHub device flow needs no loopback so suggest `github` as headless fallback).
2. `OAuthCallbackServer.wait` timeout raises `ConnectionCallbackTimeout(provider)` (code `CONNECTION_OAUTH_FAILED`; hint: browser never completed approval within timeout seconds, start one fresh login, complete approval in the opened browser, do not reuse old URLs).
3. `ConnectionManager.login` wraps `self._store.save` in try/except `ConnectionStoreUnavailable` / `StoredConnection*` and raises `ConnectionSaveFailed(provider)` (code `CONNECTION_STORE_UNAVAILABLE`; description states verification succeeded and provider grant was obtained but nothing was persisted; hint: unlock OS keyring, retry login once).
4. `OAuthBrowser.open` keeps manual-URL fallback; add `warning()` when `webbrowser.open` returns False so headless agents see a structured line naming manual open as the path.

#### Edge Cases & Error Handling

- GitHub login never constructs `OAuthCallbackServer`, so loopback classes never fire there by construction.
- Double-login overwriting the same name keeps existing replace semantics; no new error.
- `--no-input` rejection stays `click.UsageError`; no change.

### 6.5 Failure-class prose contract

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Enforces the agent-repair wording standard for every new class.

#### Interface / API

```python
# No new API; each new class fixes code/exit/retryable and carries message/description/trace/hint.
```

#### Logic / Algorithm

1. `message` names provider + outcome in one line (e.g. "The slack login was denied at Slack.").
2. `description` is 3-4 sentences: what happened, what was not changed (no token persisted / no state overwritten), whether retry of the same URL helps (never for denial/expiry/grant; yes after wait for rate-limit).
3. `trace` names the semantic path (e.g. "SlackConnectionAdapter._validate_callback rejected the loopback callback before token exchange.").
4. `hint` names the exact command or env var (`vidbyte-cli connections login slack`, `VIDBYTE_SLACK_CLIENT_ID`, `--client-secrets`).
5. No f-string interpolation of provider error bodies, emails, IDs, or paths.

#### Edge Cases & Error Handling

- N/A - prose-only contract; enforced by verification script assertions.

---

## 7. Data Model Changes

N/A - no token, metadata, or config schema changes. `ConnectionToken`, `ConnectionMetadata`, `ConnectionDocument` unchanged.

---

## 8. API Changes

N/A - no HTTP routes, no CLI flags, no stdout JSON kinds change. Machine error envelope unchanged; only `message`/`description`/`trace`/`hint` strings for new classes differ. Existing `CliErrorCode` strings reused:

| Code | Used by new classes |
|------|---------------------|
| `CONNECTION_OAUTH_FAILED` | GitHubAccessDenied, GitHubDeviceCodeExpired, SlackAccessDenied, SlackInvalidGrant, GoogleAccessDenied, GoogleInvalidGrant, ConnectionCallbackTimeout |
| `CONNECTION_CONFIGURATION_INVALID` | GitHubClientInvalid, SlackClientInvalid, GoogleClientInvalid |
| `CONNECTION_SCOPE_INSUFFICIENT` | GoogleScopeInvalid, Drive 403 re-scope path |
| `CONNECTION_RATE_LIMITED` | Slack ratelimited envelope (existing class) |
| `CONNECTION_API_UNAVAILABLE` | ConnectionLoopbackUnavailable |
| `CONNECTION_STORE_UNAVAILABLE` | ConnectionSaveFailed |
| `CONNECTION_REAUTH_REQUIRED` | Slack refresh-invalid path (existing class) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add 10 new semantic failure classes with actionable prose |
| MODIFY | `src/vidbyte_cli/lib/connections/providers/github.py` | Map device `access_denied` / `expired_token` / client errors |
| MODIFY | `src/vidbyte_cli/lib/connections/providers/slack.py` | Map callback denial, invalid grant, ratelimited envelope, refresh mapping |
| MODIFY | `src/vidbyte_cli/lib/connections/providers/google_drive.py` | Map denial, invalid_grant/client/scope, Drive 403 re-scope probe |
| MODIFY | `src/vidbyte_cli/lib/connections/oauth.py` | Raise loopback-unavailable and callback-timeout failures |
| MODIFY | `src/vidbyte_cli/lib/connections/manager.py` | Wrap store.save into save-failed failure with grant-succeeded wording |
| CREATE | `scripts/test-connection-login-failures.py` | Offline verification for every Section 10 case |
| MODIFY | `docs/design/context-provider-connections.md` | Addendum pointer to this doc (one paragraph, no rewrite) |

---

## 10. Testing Plan

### Unit Tests

- GitHub poll maps `access_denied` to GitHubAccessDenied with login-again hint — [Hidden Assumption] (assumes every poll error is expiry)
- GitHub poll maps `expired_token` to GitHubDeviceCodeExpired with fresh-code hint — [Edge Case] (boundary: code lifetime end)
- GitHub poll maps `incorrect_client_credentials` to GitHubClientInvalid naming client ID — [Silent Failure] (today returns wrong "approve before expiry" guidance with no error)
- GitHub poll with empty-string `error` proceeds to token parsing, not failure — [Edge Case]
- GitHub poll with unknown `error=bogus_future` still raises generic ConnectionOAuthFailed — [Hidden Assumption] (assumes closed error vocabulary)
- Slack callback `error=access_denied` raises SlackAccessDenied, not StateInvalid — [Silent Failure] (wrong fix: "use newest browser" vs "get approval")
- Slack callback state mismatch still raises ConnectionOAuthStateInvalid — [Edge Case] (guards new branch ordering)
- Slack `ok:false error=invalid_code` raises SlackInvalidGrant with single-use-code hint — [Hidden Failure] (fails without throwing today; collapses to generic retry)
- Slack `ok:false error=ratelimited` raises retryable ConnectionRateLimited — [Silent Failure] (today returns non-retryable OAuth failure, agent retries immediately and burns quota)
- Slack `ok:false error=rate_limited` variant also maps to RateLimited — [Edge Case] (string-variant boundary)
- Slack refresh `invalid_refresh_token` raises ReauthenticationRequired, not OAuthFailed — [Silent Failure] (wrong next action: retry refresh vs run login)
- Slack `invalid_client` on login raises SlackClientInvalid naming client ID env — [Hidden Assumption] (assumes client ID valid if non-empty)
- Google callback `access_denied` raises GoogleAccessDenied — [Hidden Failure] (denial vs forgery need opposite fixes)
- Google token `invalid_grant` raises GoogleInvalidGrant with fresh-login hint — [Silent Failure] (today says "approve before expiry" for a dead code)
- Google token `invalid_client` raises GoogleClientInvalid naming client-secrets file — [Hidden Assumption] (assumes JSON valid if present)
- Google token `invalid_scope` raises GoogleScopeInvalid naming drive.readonly default — [Edge Case] (over-scoped request boundary)
- Drive read 403 with verifying token raises ScopeInsufficient; with failing token keeps AuthRequired — [Silent Failure] (today always says "not authenticated" even when re-scoping is the fix)
- Loopback `OSError` raises LoopbackUnavailable mentioning localhost/firewall — [Hidden Failure] (bind failure masquerades as user timeout)
- Callback wait timeout raises CallbackTimeout, not generic OAuthFailed — [Edge Case] (deadline boundary)
- Keyring save failure after verify raises SaveFailed stating grant succeeded but nothing persisted — [Hidden Failure] (state mutated at provider but CLI reports plain login failure)
- Every new error document contains no `access_token`, `refresh_token`, `code`, `verifier`, or provider body substring — [Hidden Assumption] (assumes static prose never interpolates)
- Every new failure in human format renders `Hint:` line with a runnable command or env var — [Silent Failure] (missing hint looks like success to a skimming agent)

### Integration Tests

- Full GitHub denied poll through `ConnectionManager.login` with stubbed HTTP persists nothing (keyring + metadata untouched) — [Hidden Failure]
- Full Slack ratelimited `auth.test` through `status` surfaces retryable code end-to-end — [Hidden Assumption] (assumes HTTP status carries rate-limit)
- Full Google `invalid_grant` refresh through `_resolve` surfaces InvalidGrant without deleting local connection — [Hidden Failure]
- Error envelope JSON for each new class validates as `OutputDocument` with `description`, `trace`, `file_path` present — [Hidden Assumption]

### Manual / QA Test Cases

1. Given a GitHub device code, when the user presses Cancel at github.com, then stderr shows denial + fresh-login hint and no credential is stored — [Hidden Failure]
2. Given a Slack app with wrong client ID, when login runs, then stderr names `VIDBYTE_SLACK_CLIENT_ID` rather than "approve before expiry" — [Hidden Assumption]
3. Given a Google consent screen Cancel, when callback returns, then stderr says account-picker denial with Allow guidance — [Edge Case]
4. Given localhost blocked, when Slack/Google login starts, then stderr says loopback unavailable and suggests GitHub device flow — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| httpx | existing `>=0.27,<1` | Stubbed HTTP in tests; no new usage | None |
| keyring | existing `>=25.2,<26` | Fake backend in tests | None |
| GitHub device docs | `https://github.com/login/device/code`, `/login/oauth/access_token` error strings | Classification vocabulary | Low - strings stable; unknown strings fail closed |
| Slack docs | `oauth.v2.access`, `auth.test`, `ok:false error` envelope | Classification vocabulary | Low - envelope stable; variant strings covered |
| Google docs | `oauth2/v2/auth`, `oauth2.googleapis.com/token` `error` codes | Classification vocabulary | Low - OAuth2 codes stable |

---

## 12. Rollout & Deployment

- Target branch is the existing PR #49 branch `feat/context-provider-connections` (update, not a new PR); no new branch.
- No feature flags; error-only change, backward compatible (codes reused, exit statuses unchanged).
- Rollback is revert of the six modified source files; no migration.
- After merge, update `docs/design/context-provider-connections.md` addendum and close this doc to Implemented.

---

## 13. Open Questions

- [ ] Should Slack `expired_code` vs `invalid_code` get separate hints, or is one invalid-grant hint enough for agents?
- [ ] Should Drive 403 re-probe call `verify()` once (extra request) or classify on `reason` field parsing? Current design does one extra verify to avoid trusting body reasons.
- [ ] Should loopback-unavailable suggest a `--no-browser` / `--manual-code` flag as follow-up, or is the GitHub-fallback hint sufficient for this PR?

---

## 14. Alternatives Considered

### Alternative 1: New CliErrorCode per failure

- What: add `GITHUB_ACCESS_DENIED`, `SLACK_RATELIMITED_ENVELOPE`, etc. as new code strings.
- Why rejected: codes are a shipped machine contract; proliferating codes breaks existing automation branching on `CONNECTION_OAUTH_FAILED` / `RATE_LIMITED`. Distinct classes with reused codes give specific prose without breaking matchers.

### Alternative 2: Single generic OAuth failure with dynamic provider detail interpolation

- What: keep one class, interpolate provider `error_description` into hint.
- Why rejected: violates secret/body redaction rule (`cause` private, never serialized) and field-guide prose rule; dynamic bodies also drift per provider and teach agents to parse unstable strings instead of stable hints.

### Alternative 3: Retry-with-backoff inside adapters for rate-limit / polling

- What: auto-retry Slack ratelimited or GitHub slow_down with sleeps beyond current behavior.
- Why rejected: non-idempotent OAuth exchanges must not auto-retry silently; the agent caller owns retry policy via `retryable` flag. Only `slow_down`/`authorization_pending` keep their existing bounded poll.

