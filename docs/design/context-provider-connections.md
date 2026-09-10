# Design Doc: Context Provider Connections

**Status:** Implemented
**Author:** Codex  
**Created:** 2026-09-10  
**Last Updated:** 2026-09-10

---

## 1. Overview

Add local CLI authentication and read access for GitHub, Slack, and Google Drive. The new
connections command family is separate from the existing provider command family: model
provider API keys remain under provider, while named context-provider connections hold OAuth
access and refresh tokens in the operating system keyring. GitHub uses device flow, Google
Drive uses PKCE with a loopback callback, and Slack uses PKCE with a loopback callback and
user scopes. After login, connections status proves account identity and connections read
exercises a bounded provider resource API so the feature is useful end to end.

---

## 2. Goals & Non-Goals

### Goals

- Add connections login github, connections login slack, and connections login google-drive.
- Use GitHub device authorization, Google installed-app OAuth with PKCE, and Slack desktop PKCE.
- Store OAuth token envelopes only in the OS keyring.
- Store only non-secret account metadata in an atomic local document.
- Support multiple named connections per provider and profile.
- Refresh expiring tokens before status and read operations.
- Add connections list, status, logout, and bounded reads for a GitHub repository, pull request,
  Slack channel history, and Google Drive file.
- Preserve the existing stdout result envelope, stderr diagnostics, secret redaction, lazy
  dependency construction, and typed failure conventions.
- Test the complete flow with local scripted HTTP servers and fake keyrings, never live accounts.

### Non-Goals

- Do not change the existing model-provider provider login commands.
- Do not store OAuth tokens in the restricted JSON fallback file.
- Do not implement a Vidbyte backend connection service or hosted OAuth relay in this CLI-only
  change.
- Do not implement GitHub App installation-token authentication in the first version.
- Do not implement Slack bot-token installation; the local flow uses user scopes.
- Do not implement arbitrary provider discovery, MCP OAuth, context manifests, or SDK context
  conversion in this change.
- Do not promise unrestricted provider access; scopes and resource permissions remain enforced
  by each provider.

---

## 3. Background & Context

- The existing provider login flow accepts API keys for OpenAI, Claude, Grok, DeepSeek, GLM,
  Muse, and Gemini. Its model is one API key per profile/provider, which cannot represent OAuth
  refresh tokens, scopes, expiry, workspace IDs, or multiple named accounts.
- The context-integration design separates account connection from resource selection. This
  feature implements account connection plus a narrow read proof; later work can map the same
  connection and resource identifiers into SDK ContextManager items and tools.
- GitHub's official device flow is intended for CLI/headless applications. The maintained
  github/cli/oauth project is an open-source reference for device polling and local OAuth.
- Google's official Python client demonstrates InstalledAppFlow with a local server. This
  implementation uses existing httpx directly to keep the CLI dependency set small.
- Slack's current documentation supports PKCE for public desktop clients and localhost
  redirects when PKCE is enabled. Desktop Slack PKCE cannot request bot scopes, so this
  implementation requests user scopes and uses the resulting user token.
- The CLI uses classes, injected streams, lazy runtime dependencies, httpx, Pydantic, Click,
  keyring, and atomic local writes. Provider protocol behavior belongs in lib/connections,
  not in Click callbacks.

---

## 4. Requirements

### Functional Requirements

1. Accept github, slack, or google-drive (plus the `google` CLI shorthand) and a validated name
   that defaults to the canonical provider name.
2. GitHub login must request a device code, show only the user-facing verification URL and
   code on stderr, poll using the server interval, classify pending/slow-down/denied/expired
   outcomes, verify /user, and persist only after verification.
3. Google login must load an installed-app client configuration, generate state and PKCE,
   bind a one-shot loopback callback, exchange the code, verify Drive about.user, and persist
   only after verification.
4. Slack login must load a client ID, generate state and PKCE, use user_scope, bind a one-shot
   loopback callback, exchange through oauth.v2.access without a client secret, verify auth.test,
   and persist only after verification.
5. A mismatched state, OAuth error, missing code, malformed response, or timeout must never
   write keyring or metadata state.
6. Use a dedicated keyring service and a stable profile/provider/name account key. A successful
   write must read back the exact secret envelope.
7. Metadata must contain no token, authorization code, PKCE verifier, client secret, or bearer
   credential.
8. list must make no network request or secret read.
9. status must resolve, refresh when necessary, verify identity, and emit only non-secret data.
10. GitHub reads must support a repository and a pull request.
11. Slack reads must support bounded first-page channel history and must not accept arbitrary URLs.
12. Drive reads must support metadata and readable content, exporting Google Workspace documents
    and bounding ordinary-file downloads.
13. Read and auth failures must be typed and must not echo provider response bodies or tokens.
14. logout must remove local state and attempt provider revocation where safe; local removal must
    not depend on network availability.
15. Results use OutputDocument version one; progress and browser instructions use stderr.
16. help and version must not open keyring, read client secrets, start a server, open a browser,
    or make network requests.

### Non-Functional Requirements

- Use existing dependencies only: Python standard library, httpx, pydantic, click, and keyring.
- Bind callbacks to 127.0.0.1, use unpredictable state and PKCE values, accept one callback,
  and bound callback and provider requests by the configured timeout.
- Keep tokens out of logs and serialized results. Keyring failure is fatal; no plaintext OAuth
  fallback exists.
- Bound identity/API JSON responses to 1 MiB and Drive content to 10 MiB. Bound Slack history
  to 100 messages.
- Preserve profile isolation and multiple names for one provider.
- Do not retry non-idempotent OAuth exchanges.
- Keep provider-specific URLs and token shapes in adapters.

---

## 5. High-Level Design

The CLI gains a static connections command group and a lib.connections package. A connection
manager resolves a provider adapter, runs its OAuth flow, verifies the identity, and writes a
secret token envelope to a dedicated keyring store. A separate metadata store writes account
and scope information through the existing atomic writer. The order is verification, keyring,
metadata. If metadata writing fails after a keyring write, the new keyring entry is removed.

Shared OAuth code owns state, PKCE, loopback callbacks, browser launch, bounded HTTP, and
response validation. Provider adapters own URLs, scopes, token shapes, identity checks,
refresh, revoke, and resource reads. GitHub uses device polling; Google and Slack use the
common callback server.

    [Click command]
          |
          v
    [ConnectionManager] -> [GitHub / Slack / Drive adapter]
          |                         |
          v                         +--> OAuth and resource APIs
    [Keyring token envelope] + [Atomic non-secret metadata]
          |
          v
    [status or bounded read result]

---

## 6. Detailed Design

### 6.1 Connection Types and Provider Registry

**File(s):** src/vidbyte_cli/types/connection.py  
**Type:** New file

#### What it does

Defines the closed provider set, validated connection names, token envelope, metadata,
identity, resource, and read-result shapes. Secret fields use SecretStr.

#### Interface / API

    class ConnectionProvider(StrEnum): ...
    class ConnectionToken(BaseModel): ...
    class ConnectionMetadata(BaseModel): ...
    class ConnectionResource(BaseModel): ...
    class ConnectionIdentity(BaseModel): ...
    class ConnectionRead(BaseModel): ...

#### Logic / Algorithm

1. Validate provider through ConnectionProvider.
2. Accept names of 1 to 64 characters containing letters, digits, dot, underscore, or hyphen.
3. Reject empty, oversized, negative, or unsafe token values.
4. Keep metadata serializable without any secret field.

#### Edge Cases & Error Handling

- Reject names that could collide after normalization; do not silently lowercase.
- Reject unsupported metadata schemas.
- Allow a new verified login to replace the same named connection.

### 6.2 Connection Keyring and Metadata Stores

**File(s):** src/vidbyte_cli/lib/connections/store.py  
**Type:** New file

#### What it does

Stores token envelopes under the dedicated service vidbyte-cli-connections and stores only
non-secret records in connections.json. It verifies keyring writes by reading them back and
uses AtomicFileWriter for metadata.

#### Interface / API

    class ConnectionKeyringStore:
        def read(self, profile, provider, name): ...
        def write(self, profile, provider, name, token): ...
        def clear(self, profile, provider, name): ...

    class ConnectionMetadataStore:
        def list(self, profile): ...
        def read(self, profile, provider, name): ...
        def write(self, profile, metadata): ...
        def clear(self, profile, provider, name): ...

    class ConnectionStore:
        def save(self, profile, token, metadata): ...
        def load(self, profile, provider, name): ...
        def remove(self, profile, provider, name): ...

#### Logic / Algorithm

1. Derive an account key from profile, provider, and name.
2. Serialize secret token fields only inside ConnectionKeyringStore.
3. Read back after every write and compare the complete envelope.
4. Write metadata with mode 0600.
5. Remove a newly written keyring entry if metadata persistence fails.

#### Edge Cases & Error Handling

- Null/fail keyring raises ConnectionStoreUnavailable; no disk fallback is attempted.
- Malformed keyring data raises StoredConnectionSecretUnreadable without echoing it.
- Missing metadata or token raises ConnectionNotFound.
- Removing an absent record is idempotent.

### 6.3 OAuth Primitives and Loopback Callback

**File(s):** src/vidbyte_cli/lib/connections/oauth.py  
**Type:** New file

#### What it does

Provides PKCE generation, state generation, safe browser launch, a one-shot loopback callback
server, bounded form/JSON HTTP operations, and common OAuth response validation.

#### Interface / API

    class PkceChallenge:
        @classmethod
        def generate(cls): ...

    class OAuthCallbackServer:
        def __enter__(self): ...
        def __exit__(self, exc_type, exc_value, traceback): ...
        def wait(self, timeout_seconds): ...

    class OAuthHttpClient:
        def post_form(self, url, values): ...
        def get_json(self, url, headers, params=None): ...

#### Logic / Algorithm

1. Generate random state and PKCE verifier using secrets.
2. Derive the S256 challenge using hashlib and URL-safe base64 without padding.
3. Bind the callback server to 127.0.0.1 and an ephemeral port.
4. Parse one query, return a generic browser response, and stop serving.
5. Validate status, response size, JSON object shape, and provider success fields.

#### Edge Cases & Error Handling

- Timeout, wrong path, missing state, wrong state, provider error, and missing code become
  typed OAuth failures.
- Browser launch failure is non-fatal; the URL is printed to stderr for manual opening.
- Callback query values never appear in errors or results.
- Redirects are not followed for token or API requests.

### 6.4 Provider Adapter Contract

**File(s):** src/vidbyte_cli/lib/connections/providers/base.py  
**Type:** New file

#### What it does

Defines the provider adapter protocol and common token-refresh boundary. Commands and the
manager do not branch on provider HTTP details.

#### Interface / API

    class ConnectionProviderAdapter(Protocol):
        def login(self, context, scopes): ...
        def refresh(self, context, token): ...
        def verify(self, context, token): ...
        def read(self, context, token, resource): ...
        def revoke(self, context, token): ...

#### Logic / Algorithm

1. Resolve an adapter from the closed registry.
2. Let the adapter perform provider-specific login, verification, refresh, and read.
3. Refresh only inside the adapter that understands the provider token shape.
4. Accept typed resources rather than arbitrary URLs.

#### Edge Cases & Error Handling

- Adapters never return bearer tokens in identity or read models.
- Unsupported resources fail before network access.
- Scope errors remain distinguishable from invalid credentials and transport failures.

### 6.5 GitHub Device Adapter

**File(s):** src/vidbyte_cli/lib/connections/providers/github.py  
**Type:** New file

#### What it does

Implements GitHub OAuth App device authorization, identity verification, optional refresh,
revoke, repository reads, and pull-request reads.

#### Interface / API

    class GitHubConnectionAdapter:
        def login(self, context, scopes): ...
        def verify(self, context, token): ...
        def refresh(self, context, token): ...
        def read(self, context, token, resource): ...
        def revoke(self, context, token): ...

#### Logic / Algorithm

1. Require VIDBYTE_GITHUB_CLIENT_ID and optionally use VIDBYTE_GITHUB_CLIENT_SECRET.
2. POST to login/device/code with configured scopes.
3. Print verification_uri and user_code on stderr and poll login/oauth/access_token using
   the provider interval.
4. Verify GET api.github.com/user with bearer and GitHub API headers.
5. Read repos/{owner}/{repo} or repos/{owner}/{repo}/pulls/{number} after syntax validation.

#### Edge Cases & Error Handling

- Honor slow_down by increasing the polling interval and stop at expires_in.
- Classify denied, expired, rate-limited, malformed, and inaccessible-resource responses.
- Do not treat a valid user identity as access to every private repository.

### 6.6 Google Drive Adapter

**File(s):** src/vidbyte_cli/lib/connections/providers/google_drive.py  
**Type:** New file

#### What it does

Implements Google installed-app OAuth with PKCE, Drive identity verification, refresh, revoke,
metadata/content reads, and Google Workspace document export.

#### Interface / API

    class GoogleDriveConnectionAdapter:
        def login(self, context, scopes, client_secrets_path): ...
        def verify(self, context, token): ...
        def refresh(self, context, token): ...
        def read(self, context, token, resource): ...
        def revoke(self, context, token): ...

#### Logic / Algorithm

1. Read --client-secrets or VIDBYTE_GOOGLE_CLIENT_SECRETS; accept the installed client shape
   and validate the expected Google OAuth hosts.
2. Start a loopback callback, build an authorization URL with offline access, consent, and PKCE,
   then exchange the code.
3. Verify Drive about.user.
4. Fetch file metadata, export Google Docs/Sheets/Slides with suitable MIME types, and download
   ordinary files with a 10 MiB bound.

#### Edge Cases & Error Handling

- Missing client configuration, malformed JSON, denied consent, invalid grant, missing scope,
  and inaccessible file are typed failures.
- Preserve an existing refresh token when a refresh response omits one.
- Return UTF-8 content when possible and clearly labelled base64 for binary content.
- Do not claim drive.file reads arbitrary pre-existing documents.

### 6.7 Slack PKCE Adapter

**File(s):** src/vidbyte_cli/lib/connections/providers/slack.py  
**Type:** New file

#### What it does

Implements Slack OAuth v2 for a PKCE-enabled public desktop app, user-scope token exchange,
identity verification, token rotation refresh, revoke, and bounded channel history reads.

#### Interface / API

    class SlackConnectionAdapter:
        def login(self, context, scopes): ...
        def verify(self, context, token): ...
        def refresh(self, context, token): ...
        def read(self, context, token, resource): ...
        def revoke(self, context, token): ...

#### Logic / Algorithm

1. Require VIDBYTE_SLACK_CLIENT_ID; the Slack app must have PKCE and localhost enabled.
2. Request default read-only user scopes through user_scope plus repeated --scope values.
3. Exchange through oauth.v2.access with client ID, redirect URI, and PKCE verifier.
4. Extract authed_user.access_token and rotation metadata, then verify auth.test.
5. Call conversations.history with a validated channel ID and a limit from 1 through 100.

#### Edge Cases & Error Handling

- Reject ok:false, missing authed_user.access_token, missing team identity, and missing scope.
- Never request bot scopes from this localhost PKCE flow.
- Preserve the previous refresh token when rotation omits a replacement.
- Treat cursors as response data, never as user-controlled URLs.

### 6.8 Connection Manager and Runtime Context Wiring

**File(s):** src/vidbyte_cli/lib/connections/manager.py; src/vidbyte_cli/lib/runtime/context.py  
**Type:** New file; modified

#### What it does

Owns adapter selection, login persistence, token resolution, refresh, status, reads, and local
removal. ApplicationContext constructs it lazily.

#### Interface / API

    class ConnectionManager:
        def login(self, provider, name, scopes, client_secrets_path): ...
        def list(self, profile): ...
        def status(self, profile, provider, name): ...
        def read(self, profile, provider, name, resource): ...
        def logout(self, profile, provider, name): ...

#### Logic / Algorithm

1. Resolve profile and configuration once.
2. For login, run the adapter, verify identity, save token and metadata, then emit safe data.
3. For status/read, load the pair, refresh inside the five-minute safety window, persist the
   refreshed pair, and call the adapter.
4. For logout, attempt best-effort revocation and always remove local state.

#### Edge Cases & Error Handling

- Stale or revoked tokens become ConnectionReauthenticationRequired.
- Failed refresh never deletes an old usable token before the new token is verified.
- A replacement login does not destroy the existing connection until the new one succeeds.

### 6.9 CLI Commands

**File(s):** src/vidbyte_cli/commands/connections/__init__.py, login.py, list.py, status.py,
logout.py, read.py; src/vidbyte_cli/commands/__init__.py  
**Type:** New files; modified

#### What it does

Registers and presents the static command group while keeping transport and storage out of
Click callbacks.

#### Interface / API

    vidbyte-cli connections login github [--name NAME] [--scope SCOPE]
    vidbyte-cli connections login slack [--name NAME] [--scope SCOPE]
    vidbyte-cli connections login google-drive [--name NAME] [--scope SCOPE] [--client-secrets PATH]
    vidbyte-cli connections list
    vidbyte-cli connections status NAME
    vidbyte-cli connections logout NAME
    vidbyte-cli connections read github repo OWNER/REPO [--connection NAME]
    vidbyte-cli connections read github pull-request OWNER/REPO --number N [--connection NAME]
    vidbyte-cli connections read slack channel CHANNEL_ID [--connection NAME] [--limit N]
    vidbyte-cli connections read google-drive file FILE_ID_OR_URL [--connection NAME]

The CLI also accepts `google` as a shorthand for `google-drive`; persisted provider metadata
always uses the canonical `google-drive` value.

#### Logic / Algorithm

1. Click validates provider/resource choices and bounded numeric options.
2. Commands call ApplicationContext.connections() and render OutputDocument results.
3. Login progress uses diagnostics or warnings so stdout remains machine-safe.
4. Read output contains provider, resource identifiers, and provider data but never token fields.

#### Edge Cases & Error Handling

- no-input is rejected for browser/device flows.
- Missing client configuration is reported before a browser opens.
- A named connection is required when more than one matching provider connection exists.

### 6.10 Paths, Errors, and Package Wiring

**File(s):** src/vidbyte_cli/lib/config/paths.py; src/vidbyte_cli/lib/errors/codes.py;
src/vidbyte_cli/lib/errors/failures.py; src/vidbyte_cli/lib/connections/__init__.py
**Type:** Modified; modified; modified; new

#### What it does

Adds the metadata path and typed failures while preserving the single error-handler boundary.

#### Interface / API

Add stable failures for configuration, OAuth, scope, resource, store, protocol, and missing
connection conditions, with authentication, usage, operational, or storage exit semantics.

#### Logic / Algorithm

1. Add connection_metadata_file under the platform data root.
2. Add stable codes and one CliError subclass per externally visible failure.
3. Keep causes private and prose static and secret-free.
4. Keep foreign exception classification in the existing handler match.

#### Edge Cases & Error Handling

- Response bodies and exception values never become description, trace, or hint.
- Symbolic provider errors may be surfaced only when bounded and non-secret.

---

## 7. Data Model Changes

### 7.1 Connection Metadata Document

**Change type:** New

    {
      "schema_version": 1,
      "entries": [
        {
          "profile": "default",
          "provider": "github",
          "name": "work-github",
          "account_id": "12345",
          "account_label": "octocat",
          "workspace_id": null,
          "workspace_label": null,
          "scopes": ["read:user", "repo"],
          "token_type": "bearer",
          "expires_at": null,
          "storage": "keyring"
        }
      ]
    }

**Migration strategy:** No migration. Existing credential documents remain untouched. The new
file is created on first successful login and remains as an empty versioned document after the
final entry is logged out, avoiding a destructive filesystem delete during normal cleanup.

### 7.2 Connection Token Envelope

**Change type:** New; keyring-only serialized value

    {
      "schema_version": 1,
      "access_token": "<secret>",
      "refresh_token": "<secret-or-null>",
      "token_type": "Bearer",
      "expires_at": 1790000000,
    "provider_data": {}
    }

The Google installed-client ID and secret are retained inside the keyring envelope when a user
passes `--client-secrets`, so refresh does not depend on the original path. They are never copied
to `connections.json` or rendered.

**Migration strategy:** Unknown keyring schema is rejected and requires re-login; no payload
is printed.

---

## 8. API Changes

This feature adds no Vidbyte backend endpoints. It calls documented external provider APIs
directly from the local CLI.

### 8.1 GitHub OAuth and REST APIs

**Change type:** External integration

- POST https://github.com/login/device/code
- POST https://github.com/login/oauth/access_token
- GET https://api.github.com/user
- GET https://api.github.com/repos/{owner}/{repo}
- GET https://api.github.com/repos/{owner}/{repo}/pulls/{number}

### 8.2 Google OAuth and Drive APIs

**Change type:** External integration

- Configured Google authorization endpoint, normally
  https://accounts.google.com/o/oauth2/v2/auth
- Configured Google token endpoint, normally https://oauth2.googleapis.com/token
- GET https://www.googleapis.com/drive/v3/about?fields=user
- GET https://www.googleapis.com/drive/v3/files/{fileId}
- GET https://www.googleapis.com/drive/v3/files/{fileId}?alt=media
- GET https://www.googleapis.com/drive/v3/files/{fileId}/export
- POST https://oauth2.googleapis.com/revoke

### 8.3 Slack OAuth and Web APIs

**Change type:** External integration

- GET https://slack.com/oauth/v2/authorize
- POST https://slack.com/api/oauth.v2.access
- POST https://slack.com/api/auth.test
- GET https://slack.com/api/conversations.history
- POST https://slack.com/api/auth.revoke

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | docs/design/context-provider-connections.md | Source-of-truth design |
| CREATE | src/vidbyte_cli/types/connection.py | Typed providers, tokens, metadata, and reads |
| CREATE | src/vidbyte_cli/lib/connections/__init__.py | Package exports |
| CREATE | src/vidbyte_cli/lib/connections/oauth.py | Shared PKCE, callback, browser, and HTTP |
| CREATE | src/vidbyte_cli/lib/connections/store.py | Keyring secrets and metadata |
| CREATE | src/vidbyte_cli/lib/connections/manager.py | Lifecycle, refresh, and adapter registry |
| CREATE | src/vidbyte_cli/lib/connections/providers/__init__.py | Provider exports |
| CREATE | src/vidbyte_cli/lib/connections/providers/base.py | Adapter contracts |
| CREATE | src/vidbyte_cli/lib/connections/providers/github.py | GitHub flow and reads |
| CREATE | src/vidbyte_cli/lib/connections/providers/google_drive.py | Google flow and Drive reads |
| CREATE | src/vidbyte_cli/lib/connections/providers/slack.py | Slack flow and history reads |
| CREATE | src/vidbyte_cli/commands/connections/__init__.py | Connections command group |
| CREATE | src/vidbyte_cli/commands/connections/login.py | Login command |
| CREATE | src/vidbyte_cli/commands/connections/list.py | List command |
| CREATE | src/vidbyte_cli/commands/connections/status.py | Status command |
| CREATE | src/vidbyte_cli/commands/connections/logout.py | Logout command |
| CREATE | src/vidbyte_cli/commands/connections/read.py | Bounded read command |
| MODIFY | src/vidbyte_cli/commands/__init__.py | Register new group |
| MODIFY | src/vidbyte_cli/lib/runtime/context.py | Lazy manager construction |
| MODIFY | src/vidbyte_cli/lib/config/paths.py | Metadata path |
| MODIFY | src/vidbyte_cli/lib/errors/codes.py | Stable error codes |
| MODIFY | src/vidbyte_cli/lib/errors/failures.py | Typed connection failures |
| CREATE | scripts/test-context-provider-connections.py | Offline verification script |
| MODIFY | scripts/run_ci.py | Run the connection verification in the canonical gate |
| MODIFY | scripts/test_research_only_surface.py | Update the exact command-surface contract |
| MODIFY | README.md | Setup and command documentation |
| MODIFY | .env.example | Client configuration names |

---

## 10. Testing Plan

All external requests use local scripted HTTP servers or injected fake transports. No test uses
a real provider account or the developer's real keyring.

### Unit Tests

- [Edge Case] Accept names at 1 and 64 characters and reject 0 and 65.
- [Edge Case] Reject oversized tokens and Slack limits of 0 and 101.
- [Edge Case] Parse provider identity responses with optional fields absent.
- [Edge Case] Parse Drive document URLs and raw file IDs; reject unrelated URLs.
- [Edge Case] Serialize tokens with and without refresh tokens.
- [Hidden Failure] A keyring acknowledges a write but returns a different value; no metadata
  write occurs.
- [Hidden Failure] A callback receives the wrong path before the real callback; the wrong query
  is not accepted.
- [Hidden Failure] A provider returns HTTP 200 malformed JSON or Slack ok:false; no success
  model is produced.
- [Hidden Failure] A refresh omits refresh_token; the old refresh token remains.
- [Silent Failure] Assert exact authorization headers, GitHub API version header, resource paths,
  and Google export endpoint.
- [Silent Failure] Assert metadata contains no token, code, verifier, or client-secret text.
- [Silent Failure] Assert list makes zero keyring and network calls.
- [Hidden Assumption] Missing Google installed config, Slack authed_user, or GitHub device_code
  produces typed failures.
- [Hidden Assumption] Expiry as a string, null, or negative value is rejected.
- [Hidden Assumption] Two profiles and two names for one provider never cross-read or overwrite.

### Integration Tests

- [Edge Case] GitHub completes after authorization_pending and persists token plus metadata.
- [Edge Case] Google and Slack callbacks verify state and PKCE values sent to token exchange.
- [Hidden Failure] Denied consent, callback timeout, invalid grant, and transport timeout leave
  no partial local state.
- [Hidden Failure] A failed replacement login leaves the existing connection intact.
- [Silent Failure] Status refreshes once and uses the refreshed token for identity.
- [Silent Failure] Each bounded read uses the exact method, URL, header, identifier, and limit.
- [Hidden Assumption] An unavailable keyring fails without creating a plaintext token file.
- [Hidden Assumption] Browser launch returning false prints a URL and does not abort the flow.
- [Hidden Assumption] A 302 response is not followed.

### Manual / QA Test Cases

1. [Edge Case] Configure a GitHub OAuth App client ID, complete device login, and run status;
   identity appears and no token does.
2. [Edge Case] Configure a Google desktop client JSON, log in, and read a known document.
3. [Edge Case] Enable Slack PKCE, configure localhost, log in, and read an accessible channel.
4. [Hidden Failure] Cancel each consent page; no new connection appears.
5. [Hidden Failure] Remove a stored token after metadata exists; status asks for reauthentication.
6. [Silent Failure] Run login, list, status, and read with JSON output; stdout is exactly one
   JSON document and progress stays on stderr.
7. [Silent Failure] Inspect metadata and confirm scopes/account labels but no bearer credentials.
8. [Hidden Assumption] Run help/version with a failing keyring and confirm no side effects.
9. [Hidden Assumption] Configure two Slack workspaces and switch profiles; only the selected
   profile/name is used.

The executable scripts/test-context-provider-connections.py runs every case with PASS/FAIL
labels and exits non-zero unless all cases pass.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| httpx | Existing >=0.27,<1 | OAuth and provider REST calls | Provider protocol/rate-limit changes |
| keyring | Existing >=25.2,<26 | OS token storage | Headless systems may have no backend |
| pydantic | Existing >=2.6,<3 | Secret-safe validation | Schema changes need versioning |
| GitHub OAuth/REST | Device flow and api.github.com | Identity and repository reads | Scope and expiry vary by app |
| Google OAuth/Drive | Installed-app OAuth and Drive v3 | Identity and document reads | Restricted scopes may require verification |
| Slack OAuth/Web API | PKCE, oauth.v2.access, Web API | Workspace and channel reads | PKCE and workspace policy limit access |

Open-source references used during design:

- https://github.com/cli/oauth
- https://github.com/googleapis/google-api-python-client/blob/main/docs/oauth.md
- https://docs.slack.dev/authentication/using-pkce

---

## 12. Rollout & Deployment

- No feature flag is required; the command group is additive.
- Before release, configure a GitHub OAuth App with device flow, a Slack PKCE app with a
  localhost redirect and user scopes, and a Google desktop OAuth client with Drive enabled.
- Document VIDBYTE_GITHUB_CLIENT_ID, optional VIDBYTE_GITHUB_CLIENT_SECRET,
  VIDBYTE_SLACK_CLIENT_ID, and VIDBYTE_GOOGLE_CLIENT_SECRETS in README and .env.example.
- Rollback is removing the new registration and modules. Existing model credentials remain
  compatible.
- Provider app credentials must be rotated at the provider if exposed; deleting local state
  is not provider-side revocation.

---

## 13. Open Questions

- [ ] Should production GitHub use a GitHub App for per-repository least privilege?
- [ ] Should Drive default to drive.file for easier verification or drive.readonly for arbitrary
  pasted document URLs?
- [ ] Should Slack later add a Vidbyte-hosted relay for bot-token installations?
- [ ] Should the next feature connect named connections to SDK ContextManager load/tools/hybrid
  modes?

---

## 14. Alternatives Considered

### Alternative 1: Add context providers to provider login

- What: Reuse the model API-key enum and store.
- Why rejected: OAuth needs names, refresh tokens, scopes, expiry, workspace metadata, and
  provider-specific flows. The existing contract would become misleading and unsafe.

### Alternative 2: Store OAuth tokens in the restricted file fallback

- What: Copy the current API-key fallback behavior.
- Why rejected: OAuth refresh tokens are long-lived bearer credentials. This conflicts with the
  keychain requirement and unnecessarily expands the attack surface.

### Alternative 3: Add provider SDKs

- What: Add Google auth, Slack, and GitHub SDK dependencies.
- Why rejected: Existing httpx and validation primitives are enough; three SDKs expand packaging
  and transport surfaces without solving storage.

### Alternative 4: Use MCP presets for all reads

- What: Launch the SDK's existing provider MCP presets.
- Why rejected: Current MCP support expects stdio environment credentials and does not own OAuth,
  resource boundaries, or context loading. Direct adapters make the guarantees testable now.

