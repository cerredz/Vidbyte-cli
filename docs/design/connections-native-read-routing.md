# Design Doc: Connections Native-CLI Read Routing

**Status:** Approved (user auto-approved)
**Author:** OpenCode
**Created:** 2026-09-14
**Base:** `feat/context-provider-connections` (PR #49 head `962dcc1`)
**Last Updated:** 2026-09-14

---

## 1. Overview

PR #49 adds `vidbyte-cli connections login/list/status/logout/read` with direct httpx adapters for GitHub, Slack, and Google Drive. The open review question is whether `read` should instead delegate to each provider's own CLI (notably `gh`), since re-implementing provider APIs is wasteful.

This doc locks the answer: keep one stable `connections read` surface, and route behind it. GitHub reads prefer the native `gh` CLI through an allowlisted, bounded subprocess when `gh` is present and authenticated, and fall back to the existing direct httpx adapter otherwise. Slack and Drive stay direct-only because neither has a stable official CLI to delegate to. The CLI chooses the path; the agent sees one JSON contract plus a `provenance` field and a stderr hint naming the deeper native command.

---

## 2. Goals & Non-Goals

### Goals

- Keep `connections read <provider> <resource-type> <identifier>` byte-stable for existing callers.
- Prefer native `gh` for GitHub `repo` and `pull-request` reads when it is available and authenticated.
- Keep a guaranteed direct httpx fallback for GitHub when `gh` is missing, unauthenticated, or fails.
- Keep Slack (`channel`) and Drive (`file`) on the direct adapters with no native path.
- Never inject Vidbyte keyring OAuth tokens into a native CLI; each tool keeps its own auth.
- Preserve stdout-is-results, typed failures, keyring-only secrets, and offline testability.
- Tell the agent which path ran and what deeper native command to run next.

### Non-Goals

- Do not add free-form passthrough (`connections exec -- <argv...>`) in this change.
- Do not delegate `login` to `gh auth login`; Vidbyte login still writes the keyring envelope.
- Do not add native paths for Slack or Drive in this change (no stable official CLI).
- Do not sync, import, or export tokens between the Vidbyte keyring and `gh` credential storage.
- Do not change model-provider `provider login` commands.
- Do not add a backend connection service or hosted OAuth relay.

---

## 3. Background & Context

- PR #49 (`feat/context-provider-connections`) owns `types/connection.py`, `lib/connections/manager.py`, `lib/connections/providers/{github,slack,google_drive}.py`, `commands/connections/read.py`, keyring + metadata stores, and `scripts/test-context-provider-connections.py`.
- `AGENTS.md` requires stdout-is-results-only, integer-returning entry functions, and `scripts/run_ci.py` as the canonical gate.
- Field guide `typed-failures.md` requires one `CliError` subclass per visible failure, agent-native `description`/`trace`, one `match` in the handler, and no module-level helper functions. `agent-driven-command-surfaces.md` requires CLI-owned `click.Choice` enums. `implementation-restraint.md` requires matching comment density, no templated headers, and `run_ci.py` verification.
- GitHub ships `gh` with stable `--json` output and its own auth (`gh auth status`). Slack has no official CLI. Drive has only third-party forks with unstable flags and auth, so delegation there buys risk without coverage.
- Current `ConnectionRead` has `{provider, resource_type, identifier, data}` and no provenance, so callers cannot tell which transport served them.

---

## 4. Requirements

### Functional Requirements

1. `connections read` keeps the existing positional surface `provider resource_type identifier`.
2. Add `--via` with CLI-owned choices `auto`, `native`, `direct` (default `auto`).
3. Add `--show-plan` which prints the resolved native argv or direct URL plan without running it.
4. `auto` on GitHub tries native first when the probe passes, else direct; `--via native` fails typed when native is unavailable; `--via direct` never probes or spawns.
5. Native GitHub supports exactly `repo` and `pull-request`; any other combination fails before spawn with the existing resource-type validation.
6. Native argv is allowlisted: `gh repo view OWNER/REPO --json <fields>` and `gh pr view NUMBER --repo OWNER/REPO --json <fields,comments>`. No shell, no extra flags from the caller.
7. Identifier validation happens before probe/spawn using the existing `owner/repo` shape plus positive `--number` for pull requests.
8. Subprocess uses the invocation timeout, caps stdout at 1 MiB, parses `--json` strictly, and maps to `ConnectionRead.data`.
9. Every successful read sets `provenance.source` to `gh` or `direct` and echoes the executed plan on stderr when human-readable.
10. Native auth failures, missing resources, and rate limits map to the existing `ConnectionAuthenticationRequired`, `ConnectionResourceUnavailable`, and `ConnectionRateLimited` failures; native binary missing maps to a new typed failure.
11. Vidbyte OAuth tokens never appear in native argv, env, errors, or output.
12. `status` output gains `native` availability info for GitHub (`found|missing`, authenticated boolean) without failing when `gh` is absent.
13. `--help` for `read` documents `--via` and `--show-plan` in four-sentence floor per lint rules.

### Non-Functional Requirements

- Zero new runtime dependencies; `subprocess` + `shutil` from the standard library only.
- Probe result is cached per `ConnectionManager` instance; `--help` and `list` never probe or spawn.
- No network, keyring, or spawn during Click help construction.
- Preserve 100-column ruff line length, `ruff format`, strict mypy, and `python lint/run.py`.

---

## 5. High-Level Design

One command, two transports, one contract. `ConnectionReadCommand` parses the closed surface plus `--via`/`--show-plan` and builds a `ConnectionResource`. `ConnectionManager.read()` resolves the Vidbyte token as today (needed for the direct fallback and for named-connection resolution), then asks a small native layer whether `gh` can serve this resource. If yes and `--via` permits, the native GitHub adapter spawns the allowlisted argv and normalizes `--json` into `ConnectionRead`. Otherwise the existing direct adapter runs. Both paths return the same `ConnectionRead` shape with `provenance` marking the winner.

```
[connections read github repo acme/api --via auto]
        |
        v
[ConnectionManager.read] -> [NativeProbe: which(gh) + gh auth status]
        |                          | pass                  | fail
        v                          v                       v
[GitHubNativeAdapter] <-- allowlisted gh --json    [GitHubDirectAdapter (httpx, PR #49)]
        |                                              |
        +------------------+---------------------------+
                           v
              [ConnectionRead + provenance:{source, plan}]
                           |
                           v
              [OutputDocument kind=connections.read on stdout]
              [human JSON + stderr hint with deeper gh command]
```

---

## 6. Detailed Design

### 6.1 Read transport selection and provenance types

**File(s):** `src/vidbyte_cli/types/connection.py`
**Type:** Modified

#### What it does

Adds the CLI-owned transport vocabulary and stamps every read with where it came from.

#### Interface / API

    class ReadVia(StrEnum): ...
    class ReadProvenance(BaseModel): ...
    class ConnectionRead(BaseModel): ...  # adds provenance field

#### Logic / Algorithm

1. Define `ReadVia` with `AUTO`, `NATIVE`, `DIRECT` and a `cli_choices()` helper for `click.Choice`.
2. Define `ReadProvenance` with `source: Literal["gh", "direct"]` and `plan: tuple[str, ...]` (argv for native, method+URL tokens for direct).
3. Add `provenance: ReadProvenance` to `ConnectionRead` with `extra="forbid", frozen=True` preserved.
4. Keep `ConnectionProvider`, `ConnectionResource`, and token models untouched.

#### Edge Cases & Error Handling

- Unknown `source` strings fail validation rather than defaulting.
- `plan` is capped at 32 tokens of 512 chars each so a hostile native echo cannot grow output.
- Old serialized reads without `provenance` fail closed on re-parse; no silent default.

### 6.2 Native probe and bounded subprocess runner

**File(s):** `src/vidbyte_cli/lib/connections/native.py`
**Type:** New file

#### What it does

Owns native CLI discovery and safe execution so adapters hold only per-resource argv shapes.

#### Interface / API

    class NativeProbe: ...
    class NativeRunner: ...
    class NativeResult: ...

#### Logic / Algorithm

1. `NativeProbe.github()` checks `shutil.which("gh")`, then runs `gh auth status` with a 10-second ceiling; caches `{found, authenticated, version}` per manager instance.
2. `NativeRunner.run(argv, timeout_seconds)` spawns with `shell=False`, no inherited credential env beyond the process env, captures stdout/stderr with a 1 MiB cap, enforces the invocation timeout, and returns parsed JSON.
3. Version is parsed from `gh --version` best-effort (`gh version X.Y.Z`); unparseable versions record `None` rather than failing.
4. Every spawn records its argv into the result for `provenance.plan`.

#### Edge Cases & Error Handling

- Missing binary raises `ConnectionNativeCliMissing` (new typed failure); unauthenticated `gh` raises `ConnectionAuthenticationRequired("github")` so the manager can fall back on `auto`.
- Non-zero exit with `could not resolve to a Repository` / `not found` maps to `ConnectionResourceUnavailable`; `rate limit` maps to `ConnectionRateLimited`; anything else maps to `ConnectionNativeCliFailed` without echoing raw stderr beyond a bounded 500-char excerpt.
- Timeout raises `ConnectionApiUnavailable` (retryable) consistent with direct transport timeouts.
- Oversized stdout raises `ConnectionProtocolError` before JSON parsing.

### 6.3 GitHub native adapter (allowlisted `gh --json`)

**File(s):** `src/vidbyte_cli/lib/connections/providers/github_native.py`
**Type:** New file

#### What it does

Serves GitHub `repo` and `pull-request` reads from `gh --json` and normalizes them into `ConnectionRead`.

#### Interface / API

    class GitHubNativeAdapter: ...

#### Logic / Algorithm

1. Accept only `ConnectionProvider.GITHUB` with `repo` or `pull-request`; reject anything else before probe.
2. Re-validate `OWNER/REPO` with `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$` and require `number >= 1` for pull requests.
3. Build exactly `["gh", "repo", "view", identifier, "--json", "nameWithOwner,description,url,primaryLanguage,stargazerCount"]` or `["gh", "pr", "view", str(number), "--repo", identifier, "--json", "number,title,body,state,url,comments"]`.
4. Call `NativeRunner`, validate the payload as `dict[str, JsonValue]`, and wrap with `provenance={source: "gh", plan: argv}`.

#### Edge Cases & Error Handling

- `gh` emitting a JSON array or string raises `ConnectionProtocolError` (shape, not data).
- Empty `nameWithOwner` or missing `number` raises `ConnectionProtocolError`.
- Slack/Drive resources never reach this adapter; the manager guards by provider.

### 6.4 GitHub direct adapter reuse and manager routing

**File(s):** `src/vidbyte_cli/lib/connections/providers/github.py`, `src/vidbyte_cli/lib/connections/manager.py`
**Type:** Modified

#### What it does

Keeps the PR #49 httpx adapter as the fallback and adds transport routing in one place.

#### Interface / API

    class ConnectionManager: ...  # read() gains via parameter; __init__ gains native layer

#### Logic / Algorithm

1. Rename the current class inside `github.py` to `GitHubDirectAdapter` while keeping the module import alias so existing tests keep importing.
2. `ConnectionManager.__init__` constructs `NativeProbe` and `GitHubNativeAdapter` alongside the direct map; Slack/Drive registrations are unchanged.
3. `read(profile, provider, name, resource, via=ReadVia.AUTO)` resolves the named connection as today, then: `DIRECT` goes straight to the direct adapter; `NATIVE` requires GitHub + probe pass or raises typed; `AUTO` tries native on GitHub when the probe passes and falls back to direct on `ConnectionNativeCliMissing`, `ConnectionAuthenticationRequired`, or `ConnectionNativeCliFailed`.
4. Fallback preserves the original error when both paths fail by chaining (`from`) the direct error and noting the native attempt in the trace.

#### Edge Cases & Error Handling

- `--via native` on Slack/Drive raises `ConnectionProtocolError` before any probe.
- A native success never touches the Vidbyte token refresh path beyond the already-resolved read; refresh behavior from PR #49 is unchanged.
- Probe exceptions never escape as raw `OSError`; they become `ConnectionNativeCliMissing`.

### 6.5 `connections read` options and agent hint

**File(s):** `src/vidbyte_cli/commands/connections/read.py`
**Type:** Modified

#### What it does

Adds `--via` and `--show-plan` and renders provenance plus the next native command.

#### Interface / API

    vidbyte-cli connections read github repo OWNER/REPO [--connection NAME] [--via auto|native|direct] [--show-plan]
    vidbyte-cli connections read github pull-request OWNER/REPO --number N [--connection NAME] [--via ...] [--show-plan]

#### Logic / Algorithm

1. `click.Choice(ReadVia.cli_choices())` owns the vocabulary; `--show-plan` is `is_flag=True`.
2. On `--show-plan`, resolve the plan (native argv or direct method+URL) and emit it as the `OutputDocument` without spawning or HTTP.
3. On success, stdout stays the `connections.read` document (now including `provenance`); stderr gains `Provenance: <source>. Deeper: <gh command>` so agents learn the full CLI for follow-ups.

#### Edge Cases & Error Handling

- `--show-plan --via native` on Slack/Drive raises typed before probing.
- `--number` missing for `pull-request` raises typed; `--number` present for `repo` raises typed.
- `--help` text meets the four-sentence lint floor for each new option.

### 6.6 Typed failures for the native path

**File(s):** `src/vidbyte_cli/lib/errors/codes.py`, `src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/lib/errors/handler.py`
**Type:** Modified (codes, failures); read-only (handler)

#### What it does

Adds two narrowly scoped failures without changing the handler's single `match`.

#### Interface / API

    class ConnectionNativeCliMissing(CliError): ...
    class ConnectionNativeCliFailed(CliError): ...

#### Logic / Algorithm

1. Add `CONNECTION_NATIVE_CLI_MISSING` (usage, not retryable) and `CONNECTION_NATIVE_CLI_FAILED` (operational, not retryable) codes.
2. `Missing` names the binary (`gh`), the `PATH` fix, and the `--via direct` fallback. `Failed` names the allowlisted subcommand attempted and the direct fallback, with at most a 500-char stderr excerpt and never a token.
3. Handler needs no change; both subclass `CliError` and flow through the existing branch.

#### Edge Cases & Error Handling

- Native stderr containing ANSI or control chars is stripped before excerpting.
- No `file_path` is hand-written; `CliError._origin_file()` derives it.

### 6.7 Status native availability

**File(s):** `src/vidbyte_cli/lib/connections/manager.py`, `src/vidbyte_cli/commands/connections/status.py`
**Type:** Modified

#### What it does

Reports `gh` presence alongside Vidbyte connection identity without coupling auth.

#### Interface / API

- `status` document gains `native: {github: {found: bool, authenticated: bool, version: str | None}}`.

#### Logic / Algorithm

1. Manager probes best-effort inside `status` for GitHub connections only; probe failure records `found=False` rather than raising.
2. Slack/Drive statuses record `found=False` with no spawn.

#### Edge Cases & Error Handling

- A hanging `gh auth status` cannot hang `status`; the probe ceiling bounds it.
- Status never prints tokens from either store.

---

## 7. Data Model Changes

### 7.1 `ConnectionRead` gains provenance

**Change type:** Additive, backward-incompatible on re-parse (new required field)

    {
      "provider": "github",
      "resource_type": "repo",
      "identifier": "acme/api",
      "data": {"nameWithOwner": "acme/api", "...": "..."},
      "provenance": {"source": "gh", "plan": ["gh", "repo", "view", "acme/api", "--json", "..."]}
    }

**Migration strategy:** No file migration; reads are transient results, not stored documents. Existing golden assertions in `scripts/test-context-provider-connections.py` are updated to expect `provenance.source == "direct"`.

### 7.2 `ReadVia` vocabulary

**Change type:** New enum, CLI-owned

`auto | native | direct`, passed as `click.Choice`, stored only for the invocation (never persisted).

---

## 8. API Changes

No Vidbyte backend endpoints change. External integrations change only for GitHub native:

- `gh repo view OWNER/REPO --json nameWithOwner,description,url,primaryLanguage,stargazerCount`
- `gh pr view NUMBER --repo OWNER/REPO --json number,title,body,state,url,comments`
- `gh auth status` and `gh --version` for probing (best-effort, bounded).

Slack and Drive call no new external APIs.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/connections-native-read-routing.md` | Source-of-truth design (this file) |
| CREATE | `src/vidbyte_cli/lib/connections/native.py` | Probe + bounded subprocess runner |
| CREATE | `src/vidbyte_cli/lib/connections/providers/github_native.py` | Allowlisted `gh --json` adapter |
| CREATE | `scripts/test-connections-native-read-routing.py` | Offline verification for §10 |
| MODIFY | `src/vidbyte_cli/types/connection.py` | `ReadVia`, `ReadProvenance`, `ConnectionRead.provenance` |
| MODIFY | `src/vidbyte_cli/lib/connections/manager.py` | Transport routing + status native info |
| MODIFY | `src/vidbyte_cli/lib/connections/providers/github.py` | Rename to direct adapter, keep alias |
| MODIFY | `src/vidbyte_cli/commands/connections/read.py` | `--via`, `--show-plan`, provenance render |
| MODIFY | `src/vidbyte_cli/commands/connections/status.py` | Render native availability |
| MODIFY | `src/vidbyte_cli/lib/errors/codes.py` | Two new native codes |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Two new failure classes |
| MODIFY | `scripts/run_ci.py` | Run the new verification script in the gate |
| MODIFY | `scripts/test-context-provider-connections.py` | Expect `provenance.source == "direct"` |
| MODIFY | `README.md` | Document `--via`/`--show-plan` and `gh` fallback |

Creates: 3 (plus this doc). Modifies: 10. Deletes: 0.

---

## 10. Testing Plan

Harness: `scripts/test-connections-native-read-routing.py` with a fake `gh` executable on `PATH` (a Python stub emitting canned `--json`), a fake keyring, and loopback httpx for the direct fallback. No live `gh`, GitHub, Slack, or Drive.

### Unit Tests

- [Edge Case] `--via` rejects `all` and empty string at Click parsing before any probe or spawn.
- [Edge Case] `ReadProvenance.plan` with 33 tokens and a 513-char token fails validation.
- [Edge Case] `OWNER/REPO` accepts `a/b`, `A-1.B_2/c-D.E_3`; rejects `acme`, `/api`, `acme/api/extra`, `acme/api;id`, empty.
- [Edge Case] Pull-request without `--number` and `repo` with `--number 1` both raise typed before spawn.
- [Hidden Failure] Fake `gh` sleeps past the timeout; runner raises retryable `ConnectionApiUnavailable` and kills the child.
- [Hidden Failure] Fake `gh` prints 2 MiB of JSON; runner raises `ConnectionProtocolError` before parsing.
- [Hidden Failure] `gh auth status` exits 4 while `gh repo view` would succeed; `auto` falls back to direct and `provenance.source == "direct"`.
- [Silent Failure] Fake `gh` returns a JSON array instead of an object; adapter raises rather than returning `data[0]`.
- [Silent Failure] Fake `gh` returns `{}`; adapter raises rather than returning empty `data`.
- [Silent Failure] Native and direct both return `acme/api` but with different keys; test asserts the exact normalized key set per source so a field rename cannot pass silently.
- [Hidden Assumption] `gh` on `PATH` but not executable is treated as missing, not as a crash.
- [Hidden Assumption] `gh --version` printing `起诉 gh` still probes without raising.
- [Hidden Assumption] `--show-plan --via native` performs zero spawns and zero HTTP (assert via spawn/HTTP counters).

### Integration Tests

- [Edge Case] `auto` with healthy fake `gh` serves `repo` from native and records `plan[0:3] == ["gh", "repo", "view"]`.
- [Edge Case] `--via direct` with healthy fake `gh` still serves from httpx and records `source == "direct"`.
- [Edge Case] `--via native` with `gh` removed from `PATH` raises `ConnectionNativeCliMissing` naming `gh` and `--via direct`.
- [Hidden Failure] Native fails with `not found` then direct also 404s; the surfaced error chains the direct failure with the native attempt noted.
- [Silent Failure] Stdout of a successful read parses as exactly one `OutputDocument` with `kind == "connections.read"` and `provenance.source` matching the path taken.
- [Silent Failure] Human stderr hint contains the exact deeper command (`gh pr view 7 --repo acme/api --comments`) and no token substring from the fake keyring.
- [Hidden Assumption] `status` for a GitHub connection with no `gh` on `PATH` still succeeds and reports `native.github.found is False`.
- [Hidden Assumption] Slack `channel` read with `--via auto` never spawns even when fake `gh` exists (spawn counter stays 0).

### Manual / QA Test Cases

1. [Edge Case] Install `gh`, `gh auth login`, then `connections read github repo <own>/test --via auto`; provenance is `gh`.
2. [Edge Case] `connections read github repo <own>/test --via direct`; provenance is `direct` despite `gh` present.
3. [Hidden Failure] `gh auth logout`, then `auto` read still succeeds via direct fallback.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `gh` CLI | Any recent `gh`, probed best-effort | Native GitHub reads + auth status | Flag drift in `--json` fields; mitigated by allowlist + shape validation |
| httpx | Existing `>=0.27,<1` | Direct fallback, unchanged | None new |
| pydantic | Existing `>=2.6,<3` | `ReadVia`/`ReadProvenance` validation | None new |
| keyring | Existing `>=25.2,<26` | Unchanged Vidbyte token store | None new |

No new PyPI packages. No new backend routes.

---

## 12. Rollout & Deployment

- Lands stacked on PR #49; if #49 merges first, rebase this branch onto `main` and keep the manifest identical.
- No feature flag; `--via auto` preserves PR #49 behavior when `gh` is absent, so rollout is additive.
- Docs: `README.md` gains a `connections read --via/--show-plan` block and a "GitHub native (`gh`)" subsection.
- Rollback: revert this branch only; PR #49 direct adapters keep working.
- If `gh` rotates its `--json` field names, the native adapter fails closed to direct; no data migration needed.

---

## 13. Open Questions

- [ ] Should `gh issue view` join the allowlist in a follow-up, or stay out until an agent asks for it?
- [ ] Should `--show-plan` also print the direct HTTP method+URL for Slack/Drive, or is native-only enough?
- [ ] Should `doctor` surface `gh` presence repo-wide, or is per-`status` reporting sufficient?

---

## 14. Alternatives Considered

### Alternative 1: Full passthrough (`connections exec -- gh ...`)

- What: Let the caller append any native argv after `--`.
- Why rejected: Re-opens arbitrary command execution, breaks the closed provider/resource surface PR #49 added, bypasses output envelopes and typed errors, and lets write commands through a read verb.

### Alternative 2: Inject Vidbyte OAuth tokens into `gh` (`GH_TOKEN=...`)

- What: Reuse one token across both tools by exporting it to the child env.
- Why rejected: Two writers for one credential with different refresh, scope, and revocation models. Leaks bearer material into child process env and logs, and couples Vidbyte logout to `gh` state.

### Alternative 3: Native-only reads (require `gh`, drop direct GitHub httpx)

- What: Delete the direct GitHub adapter once native exists.
- Why rejected: Breaks headless/CI agents without `gh`, removes the deterministic offline test path, and makes Slack/Drive inconsistent with GitHub for no benefit.

### Alternative 4: Re-implement everything direct, ignore native CLIs

- What: Keep PR #49 as-is and never call `gh`.
- Why rejected: Duplicates `gh` auth, pagination, and field evolution forever on the one provider where a stable, scriptable CLI already exists.

---

## 15. Field-Guide Compliance

- `typed-failures.md`: two new `CliError` subclasses with static `description`/`trace`/`hint`, no bare `CliError(...)`, no module-level helper functions, no handler `match` change.
- `agent-driven-command-surfaces.md`: `ReadVia` is a `StrEnum` in `types/` with `click.Choice` at the command layer; all structured input stays argv (`--via`, `--show-plan`, existing `--connection/--number/--limit`).
- `implementation-restraint.md`: 3–6 line module docstrings, comments only on non-obvious invariants, class-first with 3–5 small methods, one-line signatures with a 1–2 line comment below each, scope limited to the §9 manifest, verified by `python scripts/run_ci.py`.
