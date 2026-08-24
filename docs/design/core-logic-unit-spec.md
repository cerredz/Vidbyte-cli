# Design Doc: Core Logic Unit Spec

**Status:** Draft
**Author:** Grok
**Created:** 2026-08-24
**Last Updated:** 2026-08-24

## 1. Overview

The CLI already has two kinds of verification: `scripts/smoke.py` boots the public command
tree and checks exit/output contracts, and `scripts/test_login_key_verification.py` drives
the real `ApiClient` against a loopback server. Neither pins the three deterministic cores
that a TS/Rust port will have to re-implement: `RetryPolicy.decide` backoff math and
Retry-After parsing, `ApiProblemMapper` status-to-failure classification, and
`ConfigResolver` five-layer precedence with provenance.

This change adds one stdlib `unittest` script, `scripts/test_core_logic.py`, that exercises
those three units in process with no sockets, no keyring, and no developer home directory,
and wires it into `scripts/run_ci.py` as a source gate. Production code under `src/` does
not change. The two Retry-After parsers already disagree; the suite pins both contracts
rather than unifying them.

## 2. Goals & Non-Goals

### Goals

- Pin `RetryPolicy.decide` for every combination of method, idempotency, attempt number,
  status, transport error class, and Retry-After form that the implementation distinguishes.
- Pin `ApiProblemMapper.from_response` for every `match` arm, the 404 `route_not_found`
  fork, request-id echoing, body-blind classification, and the mapper's digit-only
  Retry-After parser.
- Pin `ConfigResolver.resolve` for the five-layer order command → environment → selected
  profile → default profile → built-in, including mixed-layer provenance, empty-env
  handling, origin/enum/timeout validation, and read-only behavior.
- Run the suite from `scripts/run_ci.py` so local and GitHub Actions cannot drift.
- Keep the suite offline, credential-free, and free of new dependencies.

### Non-Goals

- **No pytest and no `tests/` directory.** Verification stays in `scripts/`, matching
  `test_login_key_verification.py` and `test_research_only_surface.py`.
- **No production behavior changes** under `src/`. Hostile `Retry-After: nan` currently
  yields a non-finite delay that would crash `time.sleep`; that is recorded as a follow-up,
  not fixed here.
- **No unification of the two Retry-After parsers.** Policy accepts floats and HTTP-dates;
  the mapper accepts only `str.isdigit()` after strip. Both are pinned.
- **No `CredentialResolver` tests.** Secrets have a separate order already covered by the
  login verification suite.
- **No `ConfigStore` write-conflict, digest, migration, or atomic-writer tests**, except
  the minimum store setup needed to feed the resolver a document.
- **No `ApiClient` retry-loop tests** (sleep, attempt counting at the HTTP boundary). The
  policy is tested as a pure function; the client loop stays in the login suite.
- **No CHANGELOG.md, SECURITY.md, or publish workflow.** Those are the next Tier 1 PR.
- **No AGENTS.md edit.** That file is a generated map and instructs agents to regenerate
  it rather than patch.
- **No feature test packs, FEATURE.md, or pytest plugins.**

## 3. Background & Context

### Why now

`RetryPolicy.__init__` already takes `random_source: random.Random | None` with a comment
that jitter must be deterministic for a caller, and then no caller ever injected one.
`ConfigResolver` is already environment-injectable and `VidbytePaths` is already
constructible without touching platformdirs. The seams exist; the spec does not.

`scripts/test_login_key_verification.py` covers some mapper statuses through
`ApiClient.post_direct`, which always passes `route_not_found=True`. That suite's 404 case
therefore hits `ApiRouteMissing` (`API_UNAVAILABLE`) and never `ApiResourceNotFound`
(`OPERATION_FAILED`). It also never hits 402 → `ApiCreditExhausted` (exit 5). Those branches
are why the mapper needs its own table.

### Current verification on `origin/main`

`scripts/run_ci.py` source gates, in order: ruff lint, ruff format, mypy on `src`,
compileall, `scripts/smoke.py`, `scripts/test_login_key_verification.py`,
`scripts/test_research_only_surface.py`, then isolated sdist/wheel/twine/clean-install.

`scripts/README.md` still says "No feature test packs (excluded by the approved
`design-doc-no-tests` workflow)." This PR is that workflow, and the deliverable *is* a
verification script, not a pytest pack. The README sentence is rewritten to name the
distinction.

### Field-guide constraints that apply

- `field-guide/vidbyte-cli/implementation-restraint.md`: 3–6 line module docstring, no
  templated `PURPOSE` / `FUNCTION INVENTORY` headers; verify with `python scripts/run_ci.py`;
  do not inline steps into `.github/workflows/ci.yml`.
- `field-guide/vidbyte-cli/typed-failures.md`: this PR raises no new failures. Helpers in
  the script follow the existing `scripts/` style (module-level fixtures are allowed there;
  the "no slop function after a class" rule is a `src/` review constraint).

### Two Retry-After parsers (load-bearing disagreement)

`RetryPolicy._retry_after` (`src/vidbyte_cli/lib/api/retry.py`):

- Missing header → `None` (local backoff).
- `float(value)` succeeds → `max(0.0, that float)`, including negatives, `+5`, `1e2`, `inf`.
- `float` raises `ValueError` → `email.utils.parsedate_to_datetime`; past dates clamp to
  `0.0`; unparseable → `None`.
- Does **not** strip the header value before `float`.

`ApiProblemMapper._retry_after` (`src/vidbyte_cli/lib/api/problem.py`):

- `headers.get("retry-after", "").strip()` then `int(value) if value.isdigit() else None`.
- HTTP-date, floats (`5.5`), signs (`+42`, `-1`), scientific notation, `inf`/`nan` all
  become `None`, so `ApiRateLimited` uses the static "Wait a minute…" hint.

A test that "fixes" the mapper to parse HTTP-dates would change user-visible hint text and
fight the login suite's "non-numeric Retry-After is ignored rather than crashing" case.

### Config precedence is five layers, not four

`ConfigResolver.resolve` is command → environment → selected profile → default profile →
built-in. Profile *selection* uses truthy `or` (`explicit.profile or env or
document.active_profile or "default"`). Field *values* treat exported-but-blank env as
unset via `environment.strip()`. Those are different empty-string rules and both are
pinned.

`CliApplication._configure_context` currently passes only `profile`, `output_format`, and
`color` as command overrides. `ConfigOverrides` still has `api_url` and
`request_timeout_seconds`; the suite tests the dataclass the resolver implements, not just
the flags the application currently fills.

## 4. Requirements

### Functional Requirements

1. `python scripts/test_core_logic.py` exits 0 when every case in §6.4 passes, and exits
   non-zero on the first failed assertion *or* when zero tests were collected.
2. `python scripts/run_ci.py` invokes that script as a source gate after offline smoke and
   before login key verification.
3. The suite imports production classes only. It does not subclass them, wrap them, or add
   test-only hooks in `src/`.
4. Jitter is made deterministic by injecting `random.Random` (or a `Random` subclass). No
   `freezegun`, no `time.sleep`, no bound ports.
5. HTTP-date cases use IMF-fixdate with `GMT` (`email.utils.format_datetime(..., usegmt=True)`).
   Past = 1970-01-01. Future = 2099-01-01. No asctime form (naive, local-timezone flake).
6. Config cases construct `VidbytePaths` under `tempfile.mkdtemp` and delete it in
   `finally`. They never call `VidbytePaths.default()`.
7. Config cases inject the environment mapping; they do not read or mutate real `VIDBYTE_*`
   process variables.
8. Every `ApiProblemMapper.from_response` `match` arm has at least one case, including
   404 with `route_not_found=True` and `False`.
9. A 401 body that contains a live-looking API key does not appear in `message`,
   `description`, `trace`, or `hint`.
10. Mapper 429 HTTP-date and Policy 429 HTTP-date are both asserted, and they disagree.
11. Ruff lint/format of the new file succeeds at line-length 100. Complexity stays at or
    under 10 per function by using tables and loops, not nested ladders.
12. Existing smoke, login, and research-only gates remain and still pass.

### Non-Functional Requirements

- Canonical full local CI command: `python -m pip install -e ".[dev]"` then
  `python scripts/run_ci.py`.
- Required remote checks: the existing `.github/workflows/ci.yml` matrix (Ubuntu 3.11,
  Ubuntu 3.14, Windows 3.11, macOS 3.11) running that same script. No YAML step list
  changes; the new gate is inside `run_ci.py`.
- The suite must finish in well under a second on a laptop. Any case that sleeps or
  binds a port is a defect in this design.
- No new runtime or `[dev]` dependencies.
- Windows path separators in `config_path` are compared via `Path` equality, not string
  equality with forward slashes.

## 5. High-Level Design

```text
scripts/run_ci.py
  ruff → mypy src → compileall → smoke
    → test_core_logic.py          # NEW, in-process, no I/O beyond tempfile
    → test_login_key_verification.py
    → test_research_only_surface.py
    → isolated wheel build

scripts/test_core_logic.py
  RetryPolicyTests      → RetryPolicy(random_source=...).decide(...)
  ApiProblemMapperTests → ApiProblemMapper().from_response / from_transport
  ConfigResolverTests   → ConfigResolver(store, env).resolve(overrides)
```

The pattern is "thin script, real units." `httpx.Response` is constructed in memory with an
attached `httpx.Request`. Transport failures are constructed as `httpx.ConnectError` (and
siblings) without a socket. Config uses a real `ConfigStore` over isolated `VidbytePaths`
so pydantic validation, origin normalization, and provenance take the same path as
production.

Rejected smaller version: adding a handful of cases to `test_login_key_verification.py`.
That file is a loopback HTTP harness; stuffing pure tables into it would mix process
models and still miss 404-without-`route_not_found`. Rejected larger version: pytest plus
`tests/`. That is a second runner, a new dependency, and a layout this repo has
consistently refused.

## 6. Detailed Design

### 6.1 Core logic verification script

**Files:** `scripts/test_core_logic.py`
**Type:** New

#### Responsibility

Owns the executable spec of `RetryPolicy`, `ApiProblemMapper`, and `ConfigResolver`.
Does not own command-tree contracts (smoke), login persistence (login suite), or the
research-only surface (research-only suite). Does not sleep. Does not publish.

#### Interface / API

```text
python scripts/test_core_logic.py
→ unittest.main(verbosity=2, exit=False)
→ exit 0 iff testsRun > 0 and wasSuccessful()
→ exit 1 otherwise (failures, errors, or empty collection)
```

Module docstring (3–6 lines): what the file pins, that it does not open sockets or touch
the keyring, and that the two Retry-After parsers are intentionally different.

Import style matches `scripts/test_login_key_verification.py`: `sys.path.insert` of
`src/`, then package imports with `# noqa: E402`.

#### Logic / Algorithm

1. `RetryPolicyTests` builds `RetryPolicy(random_source=random.Random(0))` unless a case
   needs a `Random` subclass that returns a fixed jitter.
2. `ApiProblemMapperTests` constructs `httpx.Response(status, headers=..., request=...)`.
3. `ConfigResolverTests.setUp` creates a temp tree and `VidbytePaths`; `tearDown` deletes
   it. `ConfigStore.save(document, expected_digest=None)` seeds a native file when a case
   needs stored profiles.
4. Assertions compare concrete types (`isinstance(error, ApiCreditExhausted)`), enum
   identity (`error.code is CliErrorCode.CREDIT_EXHAUSTED`), and numeric delay with
   `assertAlmostEqual` only where jitter is involved and the expected value is computed
   from a second `Random(0)`.
5. Expected jitter for seed 0 is computed in the test from `random.Random(0).uniform(0.0, 0.25)`,
   not hard-coded as a magic float.

#### Edge Cases & Error Handling

- Empty collection is failure, not success (`unittest` reports success when `testsRun==0`).
- Temp directory deletion uses `ignore_errors=True` so a locked Windows file does not hide
  the assertion result.
- `httpx.Response` always carries a `request=` so accessor code that wants `.request`
  cannot raise.

### 6.2 Canonical gate wiring

**Files:** `scripts/run_ci.py`
**Type:** Modified

#### Responsibility

Insert one source gate. Do not add argparse, `--stage`, or `--dist-dir` in this PR.

#### Interface / API

```text
source_gates = (
    ...
    ("offline smoke", (python, "scripts/smoke.py")),
    ("core logic", (python, "scripts/test_core_logic.py")),
    ("login key verification", (python, "scripts/test_login_key_verification.py")),
    ("research-only surface", (python, "scripts/test_research_only_surface.py")),
)
```

#### Logic / Algorithm

1. Place the new tuple immediately after smoke. Core logic is CPU-only and should fail
   faster than the loopback HTTP suite.

#### Edge Cases & Error Handling

- A non-zero exit from the new script stops the gate, same as every other source step.
- The distribution copy already excludes `__pycache__` and `.pytest_cache`; no exclude
  change is required.

### 6.3 Scripts README

**Files:** `scripts/README.md`
**Type:** Modified

#### Responsibility

Replace the "No feature test packs" non-goal with a precise boundary, and index the new
file.

#### Logic / Algorithm

- Non-goal becomes: no pytest, no `tests/` tree, no command-behavior feature packs.
  Deterministic specs of lib units live as `scripts/test_*.py`.
- Files list adds `test_core_logic.py` — retry policy, problem mapping, config
  precedence. Open when those three modules change.
- Log line dated 2026-08-24.

### 6.4 Case catalogue

This section is the implementation source of truth. A case that is listed and not
asserted is an incomplete implementation. A case that is asserted and not listed is
scope creep unless it is a mechanical consequence of a listed row (for example
iterating both 400 and 422 from one table).

Constants are read from production behavior, not re-declared as a second policy:

| Name | Value |
| --- | --- |
| `_MAX_ATTEMPTS` | 3 |
| `_BASE_DELAY_SECONDS` | 0.25 |
| `_UNJITTERED_CAP_SECONDS` | 4.0 |
| `_JITTER_SECONDS` | 0.25 |
| `_MAXIMUM_DELAY_SECONDS` | 10.0 |
| `_SAFE_METHODS` | GET, HEAD, OPTIONS |
| `_RETRYABLE_STATUSES` | 408, 429, 502, 503, 504 |
| `_RETRYABLE_ERRORS` | ConnectError, ConnectTimeout, ReadTimeout, RemoteProtocolError |
| `DEFAULT_API_URL` | `https://vidbyte-backend.onrender.com` |
| Default timeout | 30.0, `ge=1.0`, `le=300.0` |
| Request-id bound | length in `1..=128` |

#### 6.4.1 RetryPolicy — repeatability and transience

Unless noted, attempt is 1 and the policy uses `Random(0)`.

| # | Request | Outcome | Expected |
| --- | --- | --- | --- |
| R1 | GET, attempt 3, 503 | no retry | attempts exhausted even though transient |
| R2 | GET, attempt 4, 503 | no retry | |
| R3 | GET/HEAD/OPTIONS × 408,429,502,503,504 | retry | loop the pairs |
| R4 | GET × 401,403,404,400,409,422,500,501,505,200,302,418 | no retry | 500 is **not** retryable; 502–504 are |
| R5 | POST, `has_idempotency_key=False`, 503 | no retry | priced mutation without a key |
| R6 | POST, `has_idempotency_key=False`, 429 | no retry | transience does not override repeatability |
| R7 | POST, `has_idempotency_key=True`, 503 | retry | |
| R8 | POST, `has_idempotency_key=True`, 401 | no retry | key does not make a rejection transient |
| R9 | PUT, PATCH, DELETE, TRACE, CONNECT, empty method, `"GET "` (trailing space) | 503, no retry | only exact GET/HEAD/OPTIONS or POST+key |
| R10 | `"get"` / `"Get"` / `"pOsT"`+key | 503, retry | `.upper()` is applied |
| R11 | GET + ConnectError, ConnectTimeout, ReadTimeout, RemoteProtocolError | retry | |
| R12 | GET + WriteTimeout, PoolTimeout, TimeoutException, ProtocolError, ProxyError, UnsupportedProtocol, DecodingError, TooManyRedirects | no retry | sibling classes that are HTTPError but not in the tuple |
| R13 | POST without key + ConnectError | no retry | transport failure does not make a mutation repeatable |
| R14 | GET + 429, attempt 3 | no retry | max-attempts is checked before transience |

#### 6.4.2 RetryPolicy — delay math

Local curve: `min(0.25 * 2**(attempt-1), 4.0) + uniform(0, 0.25)`, then `min(..., 10)`.
Local path never sets `delay_clamped`.

| # | Setup | Expected delay / flags |
| --- | --- | --- |
| D1 | GET 503, attempt 1, Random(0), no header | `0.25 + Random(0).uniform(0, 0.25)`, not clamped |
| D2 | GET 503, attempt 2, Random(0), no header | `0.50 + Random(0).uniform(0, 0.25)`, not clamped |
| D3 | GET 503, attempt 1, `Random` subclass `uniform→0` | exactly 0.25, not clamped |
| D4 | GET 503, attempt 1, `uniform→100` | 10.0 **and `delay_clamped is False`** (local path does not set the flag even when the 10s cap binds) |
| D5 | GET 429, `Retry-After: 5` | 5.0, not clamped, retry True |
| D6 | GET 429, `Retry-After: 10` | 10.0, **not** clamped (`>` is strict) |
| D7 | GET 429, `Retry-After: 10.0001` | 10.0, clamped True |
| D8 | GET 429, `Retry-After: 100` | 10.0, clamped True |
| D9 | GET 429, `Retry-After: 0` | 0.0, retry True (immediate repeat is still a retry) |
| D10 | GET 429, `Retry-After: -1` | 0.0 via `max(0.0, float(...))`, retry True |
| D11 | GET 429, `Retry-After: +5` | 5.0 (`float` accepts a leading plus) |
| D12 | GET 429, `Retry-After: 2.5` | 2.5 |
| D13 | GET 429, `Retry-After: 1e2` | 10.0, clamped True (`float("1e2")==100`) |
| D14 | GET 429, `Retry-After: inf` | 10.0, clamped True (`inf > 10`) |
| D15 | GET 429, `Retry-After: nan` | `math.isnan(delay_seconds)`, `delay_clamped is False` (NaN comparison is false). **Pin, do not fix.** Follow-up: `time.sleep(nan)` raises `ValueError`. |
| D16 | GET 429, `Retry-After: 5 ` (trailing space) | 5.0 (`float` allows surrounding whitespace; mapper also strips — agreement on this form) |
| D17 | GET 429, missing header | local backoff, not clamped |
| D18 | GET 429, empty header `""` | `float("")` fails, date parse fails, local backoff |
| D19 | GET 429, `Retry-After: not-a-date` | local backoff |
| D20 | GET 429, HTTP-date 1970-01-01 GMT | delay 0.0, retry True, not clamped |
| D21 | GET 429, HTTP-date 2099-01-01 GMT | delay 10.0, clamped True |
| D22 | GET ConnectError (no response) | local backoff; server delay is None |
| D23 | Header name `Retry-After` mixed case | treated as `retry-after` (httpx headers are case-insensitive) |

Do not use the RFC 850 or asctime HTTP-date forms. `parsedate_to_datetime` on a naive
asctime uses the local timezone and will flake across the CI matrix.

#### 6.4.3 ApiProblemMapper — status table

`from_response` reads status and `x-request-id` only. Body is irrelevant except as a
leakage probe. `route_not_found` is consulted only on 404.

| # | Status | `route_not_found` | Class | `code` | `exit_status` | `retryable` |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | 401 | either | `ApiCredentialsRejected` | AUTH_REQUIRED | 4 | False |
| M2 | 403 | either | `ApiPermissionDenied` | AUTH_REQUIRED | 4 | False |
| M3 | 402 | either | `ApiCreditExhausted` | CREDIT_EXHAUSTED | 5 | default False |
| M4 | 404 | False | `ApiResourceNotFound` | OPERATION_FAILED | 1 | False |
| M5 | 404 | True | `ApiRouteMissing` | API_UNAVAILABLE | 1 | default False |
| M6 | 409 | either | `ApiRequestConflicted` | INVALID_ARGUMENT | 2 | False |
| M7 | 400 | either | `ApiRequestRejected` | INVALID_ARGUMENT | 2 | False |
| M8 | 422 | either | `ApiRequestRejected` | INVALID_ARGUMENT | 2 | False |
| M9 | 429 | either | `ApiRateLimited` | API_UNAVAILABLE | 1 | **True** |
| M10 | 500 | either | `ApiUnavailable` | API_UNAVAILABLE | 1 | True |
| M11 | 502, 503, 504, 501, 599 | either | `ApiUnavailable` | API_UNAVAILABLE | 1 | True |
| M12 | 418 | either | `ApiOperationFailed` | OPERATION_FAILED | 1 | False |
| M13 | 302, 301, 307, 308 | either | `ApiOperationFailed` | OPERATION_FAILED | 1 | False |
| M14 | 200, 204 | either | `ApiOperationFailed` | OPERATION_FAILED | 1 | False |
| M15 | 499 | either | `ApiOperationFailed` | OPERATION_FAILED | 1 | False |

`route_not_found=True` on 401 still yields `ApiCredentialsRejected` (M16): the flag is
404-only.

#### 6.4.4 ApiProblemMapper — headers, body, transport

| # | Setup | Expected |
| --- | --- | --- |
| H1 | 401, `x-request-id: req_abc` | `error.request_id == "req_abc"` |
| H2 | 401, no request-id | `request_id is None` |
| H3 | 401, request-id length 0 | `None` (bound is `1 <= len <= 128`) |
| H4 | 401, request-id length 1 | kept |
| H5 | 401, request-id length 128 | kept |
| H6 | 401, request-id length 129 | `None` |
| H7 | 429, `Retry-After: 42` | hint contains `"42"` |
| H8 | 429, `Retry-After: 042` | hint contains `"42"` (`int("042")==42`); `isdigit()` is true |
| H9 | 429, HTTP-date 2099 GMT | hint is the static minute/poll wording, **not** a parsed date. Contrast D21. |
| H10 | 429, `Retry-After: 5.5` | static hint (`.isdigit()` false). Contrast D12. |
| H11 | 429, `Retry-After: -1` | static hint. Contrast D10. |
| H12 | 429, `Retry-After: +42` | static hint. Contrast D11. |
| H13 | 429, empty / missing Retry-After | static hint |
| H14 | 429, `Retry-After: 42` with surrounding spaces | hint contains `"42"` (mapper strips) |
| H15 | 401, JSON body `{"detail": "vb_live_" + "a"*32}` | that string is absent from message, description, trace, hint |
| H16 | `from_transport(ConnectError)` | `ApiUnreachable`, `API_UNAVAILABLE`, retryable True |
| H17 | `from_transport(ReadTimeout)` | same class — transport type is not classified further |
| H18 | 429 + request-id + Retry-After together | both fields populated independently |

#### 6.4.5 ConfigResolver — precedence and provenance

Each case asserts both the winning value and `provenance[ConfigField.*]`.

| # | Setup | Expected |
| --- | --- | --- |
| C1 | no file, empty env, no overrides | built-in: `DEFAULT_API_URL`, HUMAN, AUTO, 30.0; all provenance `BUILT_IN`; `config_path is None`; profile `"default"` |
| C2 | `resolve()` vs `resolve(None)` vs `resolve(ConfigOverrides())` | identical |
| C3 | command override on every field | those values, provenance `COMMAND` |
| C4 | env `VIDBYTE_API_URL`, `VIDBYTE_OUTPUT_FORMAT`, `VIDBYTE_COLOR`, `VIDBYTE_REQUEST_TIMEOUT_SECONDS`, `VIDBYTE_PROFILE` over a stored default profile with different values | env wins, provenance `ENVIRONMENT`, profile name from `VIDBYTE_PROFILE` |
| C5 | stored selected profile `work` with distinct settings, no env, no overrides, `active_profile=work` | selected values, provenance `SELECTED_PROFILE`, profile `work` |
| C6 | `ConfigOverrides(profile="work")` beats `VIDBYTE_PROFILE=other` beats `active_profile` | profile `work` |
| C7 | `VIDBYTE_PROFILE=work` beats `active_profile=other` | profile `work` |
| C8 | named profile missing, default profile present | default profile values, provenance `DEFAULT_PROFILE`, profile name still the requested missing name |
| C9 | file exists with only profile `work` (no `default` key), resolve profile `other` | built-in values, provenance `BUILT_IN`, `config_path` is the native file (file exists, no matching profile) |
| C10 | mixed layers: command `output_format=JSON`, env `VIDBYTE_COLOR=never`, stored selected timeout 15, built-in api_url | four different provenance entries on one `ResolvedConfig` |
| C11 | `VIDBYTE_API_URL=""` or whitespace-only | treated as unset (field-value strip rule), not as an empty origin |
| C12 | `VIDBYTE_PROFILE=""` | treated as unset (truthy `or` rule), falls through to active/default |
| C13 | `VIDBYTE_PROFILE="  "` (whitespace, truthy) | `InvalidConfigOverride` (fails `ProfileName` pattern) |
| C14 | `VIDBYTE_PROFILE="has space"` | `InvalidConfigOverride` |
| C15 | `VIDBYTE_API_URL="not-a-url"` | `InvalidConfigOverride` |
| C16 | `VIDBYTE_API_URL="http://example.com"` | `InvalidConfigOverride` (non-loopback HTTP) |
| C17 | `VIDBYTE_API_URL="http://127.0.0.1"` | succeeds, loopback HTTP allowed, normalized origin |
| C18 | `VIDBYTE_API_URL="http://localhost"` | succeeds |
| C19 | `VIDBYTE_API_URL="http://[::1]"` | succeeds (IPv6 loopback) |
| C20 | `VIDBYTE_API_URL="https://example.com/v1"` | `InvalidConfigOverride` (path forbidden) |
| C21 | `VIDBYTE_API_URL` with userinfo, query, or fragment | `InvalidConfigOverride` (one case each, or parametrize) |
| C22 | `VIDBYTE_API_URL="https://host:8443"` | port preserved |
| C23 | `VIDBYTE_API_URL="https://host/"` | normalizes to no path |
| C24 | `VIDBYTE_OUTPUT_FORMAT="JSON"` (uppercase) | `InvalidConfigOverride` — env is case-sensitive; Click lowercases, the resolver does not |
| C25 | `VIDBYTE_OUTPUT_FORMAT="json"` / `"jsonl"` / `"none"` / `"human"` | those enums |
| C26 | `VIDBYTE_COLOR="Always"` | `InvalidConfigOverride` |
| C27 | `VIDBYTE_COLOR="always"` / `"auto"` / `"never"` | those enums |
| C28 | `VIDBYTE_REQUEST_TIMEOUT_SECONDS="abc"` | `InvalidConfigOverride` |
| C29 | `VIDBYTE_REQUEST_TIMEOUT_SECONDS="0.5"` | `InvalidConfigOverride` (`ge=1.0`) |
| C30 | `VIDBYTE_REQUEST_TIMEOUT_SECONDS="301"` | `InvalidConfigOverride` (`le=300.0`) |
| C31 | `VIDBYTE_REQUEST_TIMEOUT_SECONDS="1"` and `"300"` | succeed at the bounds |
| C32 | `VIDBYTE_REQUEST_TIMEOUT_SECONDS="30.5"` | 30.5 |
| C33 | command `api_url=""` | `api_url is not None`, so COMMAND wins, then `api_url or DEFAULT_API_URL` substitutes the default **while provenance stays COMMAND**. Pin this quirk. |
| C34 | after C1, `paths.config_file()` does not exist | resolve is read-only; no implicit write or migration |
| C35 | native file and legacy file both present with different `api_url` | native wins (store rule the resolver consumes) |
| C36 | legacy file only | settings come from legacy, `config_path` equals `paths.legacy_config_file()` |
| C37 | env values with surrounding whitespace (`" json "`, `" never "`, `" 45 "`) | stripped then parsed |
| C38 | `InvalidConfigOverride.code is CONFIG_INVALID` and does not echo the bad value in message/description/trace/hint | |
| C39 | profile name is not in `provenance` | only the four `ConfigField` members are keys |
| C40 | stored selected profile, env overrides only timeout | other fields stay `SELECTED_PROFILE`, timeout is `ENVIRONMENT` |

C9 requires writing a `ConfigDocument` whose `profiles` map has no `"default"` key.
`require_profiles` only demands a non-empty map, so `{ "work": ProfileConfig() }` is
valid. That is the case that distinguishes "file on disk" from "selected/default
profile source."

C35/C36 use `ConfigStore.load`'s native-over-legacy rule. They are in scope because the
resolver's `snapshot.path` and `stored` map are exactly how those files become
provenance. They are not migration tests: `StateMigration` is never called.

## 7. Data Model Changes

N/A - no schema, document, or persisted field changes. Tests construct already-valid
`ConfigDocument` / `ProfileConfig` values.

## 8. API Changes

N/A - no public CLI flags, env vars, error codes, or JSON document kinds are added or
removed. `RetryDecision`, `ResolvedConfig`, and `CliError` subclasses keep their current
fields.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/core-logic-unit-spec.md` | This design doc. |
| CREATE | `scripts/test_core_logic.py` | Unit spec for retry, mapper, and config precedence. |
| MODIFY | `scripts/run_ci.py` | Invoke the new script as a source gate after smoke. |
| MODIFY | `scripts/README.md` | Index the new script; correct the feature-test-pack non-goal. |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| unittest | stdlib | Test runner | None — already used implicitly by the ecosystem; no new pin. |
| httpx | existing runtime dep | In-memory `Response` / `HTTPError` construction | Constructor differences across 0.27–<1; attaching `request=` avoids the common footgun. |
| tempfile / shutil | stdlib | Isolated config trees | Windows file locking; `ignore_errors=True` on teardown. |
| pytest | N/A | Not added | Adding it would create a second runner. |

## 11. Rollout & Deployment

- Land as a draft PR into `main`. No version bump, no tag, no PyPI publish.
- Rollback is revert of the PR. The suite is verification-only; revert restores the
  previous gate list and deletes the spec.
- No feature flag. A failing case is a merge blocker, which is the point.
- Follow-up PR (not this one): `SECURITY.md`, `CHANGELOG.md`, tag-triggered OIDC publish.
- Follow-up (not this one): reject non-finite `Retry-After` in `RetryPolicy._retry_after`
  so `time.sleep` cannot raise `ValueError` on `nan`.

## 12. Open Questions

- [x] pytest vs `scripts/` unittest — resolved: `scripts/` unittest, matching existing
  verification scripts. Flip only if the login suite is rewritten into the same runner.
- [x] One file vs three — resolved: one file, three `TestCase` classes. Split into
  `test_retry_policy.py` / `test_api_problem_mapper.py` / `test_config_resolver.py` only
  if ruff C90 cannot be satisfied with tables. Prefer tables over a split.
- [x] Unify Retry-After parsers — resolved: no, pin the disagreement.
- [x] Fix `Retry-After: nan` — resolved: pin current behavior, do not fix in this PR.
- [ ] N/A - no unresolved questions remaining.

## 13. Alternatives Considered

### Add cases to `test_login_key_verification.py`

- What: Extend the existing loopback suite with policy/mapper/config assertions.
- Why rejected: That file owns wire format and persistence. It always calls
  `post_direct` (`route_not_found=True`), so it cannot see `ApiResourceNotFound`. Mixing
  in-process tables with a live server makes failures slower and harder to locate.

### pytest + `tests/`

- What: The SDK layout.
- Why rejected: New dependency, new top-level directory, second runner next to `scripts/`.
  This repo's gate is `run_ci.py` invoking scripts. The seven-PR program also forbade
  `tests/`; even though that program is done, the remaining grain is `scripts/test_*.py`.

### Production clock injection for HTTP-date

- What: Add `now: Callable[[], datetime]` to `RetryPolicy`.
- Why rejected: Requires a `src/` change for a test convenience. Far-past / far-future
  GMT dates make wall-clock skew irrelevant without a new seam.

### Unify the Retry-After parsers

- What: Teach the mapper to parse HTTP-dates and floats the way the policy does.
- Why rejected: Changes the 429 hint users see, and contradicts the login suite. A
  unification PR can happen later with its own contract change; this spec would then be
  updated.

### Skip C35/C36 (legacy vs native)

- What: Keep the suite strictly inside `ConfigResolver` by injecting a fake store.
- Why rejected: There is no store protocol to fake, and faking it would not prove that
  `snapshot.path is None` is what forces `BUILT_IN`. Using the real store over isolated
  paths is the smaller complete design.
)
