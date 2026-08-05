# Design Doc: Python CLI Platform and Research Harness Program

**Status:** Approved
**Author:** Codex
**Created:** 2026-07-26
**Last Updated:** 2026-07-26
**Approved:** 2026-07-26

---

## 1. Overview

This program turns the existing Python Vidbyte CLI scaffold into a production-quality,
reusable client platform and then adds a first-class research harness surface. The work is
intentionally split across seven reviewable pull requests: four PRs build cross-harness
application, output, configuration, credential, HTTP, idempotency, polling, packaging, and
CI capabilities; two PRs add research-owned domain, application, presentation, and command
code without coupling it to HTTP; and a final PR connects those commands to the fully
implemented Vidbyte research API. The CLI remains a thin Python client: research execution,
billing, persistence, provider selection, and orchestration stay on the Vidbyte backend.

---

## 2. Goals & Non-Goals

### Goals

- Keep the CLI in Python and build on the accepted Click, Pydantic, and HTTPX stack already
  merged into `origin/main`.
- Preserve the accepted architecture rule that commands are thin, services own behavior,
  Pydantic models own boundary validation, and HTTP is centralized.
- Establish reusable CLI infrastructure that future Vidbyte harnesses can consume without
  copying research-specific code.
- Separate application composition, human/machine output, typed errors, configuration,
  credentials, HTTP transport, retry policy, idempotency, polling, terminal handling, and
  operation recovery into explicit reusable collaborators.
- Keep `--help`, `--version`, configuration reads, and other offline commands free of
  credential and network I/O.
- Add a first-class `vidbyte-cli research` command group for persistent research threads,
  runs, sources, artifacts, capabilities, and exports.
- Support the existing PR #284 mutation routes:
  `POST /research/run`, `POST /research/threads/{thread_id}/run`, and
  `POST /research/runs/{run_id}/continue`.
- Define the API-key read/export contract that the final integration PR assumes is fully
  implemented.
- Provide stable machine-readable output, documented process exit semantics, coarse
  long-run watching, and safe Ctrl-C behavior.
- Store API credentials in the operating-system keyring where available, support
  `VIDBYTE_API_KEY` for automation, and retain a permission-restricted compatibility
  fallback.
- Follow platform-native config/cache/state locations while safely recognizing the current
  `~/.vidbyte` layout.
- Make every PR independently lint-clean, type-clean, compile-clean, smoke-clean,
  package-clean, and green in GitHub Actions without adding feature test files.
- Open exactly seven draft PRs in a dependency stack, with a separate self-review,
  refinement pass, local CI run, and remote-check wait for every PR.

### Non-Goals

- No research-agent, search-provider, Firecrawl, Brave, LLM, credit-metering, MongoDB,
  Inngest, or backend orchestration logic in this repository.
- No changes to Vidbyte PR #284 or any backend repository.
- No frontend real-time agent-step view. The CLI exposes coarse run state and aggregate
  progress only; detailed execution traces remain a web-only capability.
- No new `tests/` files or feature test modules under this no-tests workflow. Existing
  smoke verification is expanded, and lint/type/build/package gates remain mandatory.
- No implementation of research chat, in-depth artifact generation, favorites, deletion,
  “more like this,” team sharing, automatic research, or monitoring from v2-v4.
- No local persistence of research artifacts, paper HTML, agent context, provider
  credentials, or full prompts in debug logs or operation journals.
- No client-side pricing tables, preset source counts, provider lists, export-provider
  lists, or resumability rules that the server can own.
- No replacement of the accepted dynamic manifest harness mechanism under
  `lib/harness/` and `harnesses/`.
- No general plugin system and no migration from Click to Typer or oclif.
- No claim to the `vidbyte` executable in this program. The `vidbyte-skills` npm package
  currently owns that binary name, so the Python entry point remains `vidbyte-cli`.
- No package publication in these seven PRs; the repository becomes publication-ready,
  but publishing is a separately authorized release action.

---

## 3. Background & Context

- The local checkout is on the closed TypeScript branch
  `feat/universal-cli-scaffold`, but GitHub `main` is
  `289d196ecee83a98d026dc2feacc16a879b14c9c` and already contains the merged Python
  implementation from PR #2 plus PR #3's review resolutions. This design targets
  `origin/main`, not the stale local branch.
- The canonical Python scaffold requires Python 3.11+, uses a `src/` layout, and depends on
  Click, Pydantic v2, and HTTPX. Ruff and strict mypy are configured. There is no GitHub
  Actions workflow and no canonical all-in-one local CI script.
- Existing commands deliberately raise “not implemented” errors. Existing seams include
  `ApiClient`, endpoint groups, `CredentialStore`, `ConfigStore`, `VidbytePaths`,
  `CliError`, `Logger`, `RunRenderer`, `HarnessContext`, `BaseHarness`,
  `InvocationBuilder`, `HarnessCatalog`, and `HarnessRegistry`.
- Existing accepted harness architecture distinguishes `lib/harness/` as reusable mechanism
  from `harnesses/` as optional hand-written policy. Backend manifests can generate dynamic
  `vidbyte-cli harness <name> <command>` trees, while hand-written harness packages enrich
  individual UX.
- Research is deliberately different from a generic manifest-only harness. It is a
  persistent product surface with threads, runs, sources, artifacts, exports, pagination,
  and long-lived status semantics. It therefore receives a first-class top-level
  `research` group and a feature-owned package, while reusing generic CLI infrastructure.
- PR #284 currently exposes only API-key mutation/admission routes. Its accepted request
  model includes prompt, schema version, size, target source/search counts, resource kinds,
  domain filters, publication date, and language. Mutations require `Idempotency-Key` and
  return `{thread_id, run_id, status}` with HTTP 202.
- PR #284's known run states are `admitting`, `accepted`, `running`, `completed`, `partial`,
  `failed`, `cancelled`, and `credit_exhausted`; only `partial`, `failed`, and
  `credit_exhausted` are currently resumable.
- The backend deliberately keeps product reads in authenticated Next.js server actions
  today. The final CLI integration requires equivalent API-key read/export routes. This
  design specifies the assumed public contract rather than changing the backend.
- Click's application context is the accepted place to attach invocation-owned state, and
  building the command tree must remain synchronous and free of service I/O. HTTPX's
  long-lived synchronous `Client` fits this CLI because it provides connection pooling and
  explicit connect/read/write/pool timeouts without introducing an asyncio lifecycle.
- The Python `keyring` package provides a portable interface to macOS Keychain, Windows
  Credential Locker, and Linux Secret Service/KWallet, but headless Linux may not have a
  usable backend. The design therefore requires a detected secure store plus an explicit,
  permission-restricted fallback rather than pretending every installation has a keyring.
- `platformdirs` distinguishes configuration, cache, state, and data across Windows,
  macOS, and XDG platforms. The CLI will adopt those locations without destructively
  deleting the existing `~/.vidbyte` directory.
- The project field guide path `field-guide/vidbyte-cli/init.md` does not exist, so there
  are no additional field-guide constraints for this design.

---

## 4. Requirements

### Functional Requirements

1. The implementation MUST be split into exactly seven PRs in the order defined in
   Section 11.
2. Each PR MUST have one responsibility, a bounded manifest, its own self-critique and
   refinement pass, a full local CI run, and green required GitHub checks.
3. The design document MUST be the first commit in PR 1 and inherited by the stacked
   descendants.
4. The CLI MUST remain Python 3.11+ using Click, Pydantic v2, and synchronous HTTPX.
5. `CliApplication.run(argv)` MUST return an integer and MUST NOT call `sys.exit`.
   `SystemExit` is allowed only in the console/module entry shim.
6. A per-invocation `ApplicationContext` MUST own lazy factories for configuration,
   credentials, HTTP, output, harness services, and research services.
7. Constructing or rendering the command tree MUST NOT read credentials, mutate files, or
   contact the network.
8. All stdout/stderr access MUST pass through injected `IOStreams`; command and application
   code MUST NOT call bare `print`.
9. Stdout MUST contain command results only. Progress, warnings, diagnostics, and errors
   MUST go to stderr.
10. The root CLI MUST support `--format human|json|jsonl|none`, `--json` as an alias for
    `--format json`, `--profile`, `--no-input`, `--color auto|always|never`, and `--debug`.
11. `--json` and `--format json` MUST emit exactly one JSON result document. Streaming
    state transitions MUST require `--format jsonl`.
12. Machine output MUST contain `schema_version` and `kind` fields and use stable,
    documented field names. Human output is not a parsing contract.
13. Color and cursor movement MUST be disabled when stderr is not a TTY, `TERM=dumb`, or
    `NO_COLOR` is set; status MUST never be conveyed by color alone.
14. The CLI MUST use typed errors with stable error code, exit code, safe message,
    optional hint, retryability, request ID, and cause. Unexpected failures MUST not expose
    stack traces unless `--debug` is active.
15. The documented base exit codes MUST be: `0` success, `1` operational failure,
    `2` usage error, `3` partial research outcome under `--exit-status`, `4`
    authentication failure, `5` credit exhaustion, `70` internal software error, and
    `130` user interrupt.
16. Configuration precedence MUST be command option, environment, selected profile,
    user config, built-in client default, then server-owned product default.
17. Configuration keys MUST be typed and allow-listed; `config set` MUST reject unknown
    keys.
18. Configuration and local state writes MUST use temporary sibling files, flush, atomic
    replace, restrictive permissions where supported, and schema-versioned Pydantic models.
19. The CLI MUST recognize legacy `~/.vidbyte` config, credentials, and manifest cache
    paths. Migration MUST be copy/verify-first and MUST NOT delete the legacy copy.
20. Credential resolution MUST be `VIDBYTE_API_KEY`, then OS keyring, then an explicitly
    warned permission-restricted legacy/file fallback.
21. `login` MUST read a token from hidden interactive input or stdin (`--with-token`);
    it MUST NOT accept a raw token as a normal command-line argument.
22. Login MUST verify the credential before storing it. Logout MUST be idempotent.
23. The credential keyring account MUST be scoped by profile and API host so a token cannot
    silently cross hosts.
24. `ApiClient` MUST receive resolved settings and credentials through its constructor; it
    MUST NOT read environment variables itself.
25. One shared HTTPX `Client` MUST be reused during an invocation and closed deterministically.
26. HTTP requests MUST set authentication, user agent, CLI version, request ID, accepted
    content types, and idempotency headers where applicable.
27. The HTTP layer MUST enforce connect/read/write/pool timeouts, a bounded response size,
    content-type checks, one body read, JSON decoding, Pydantic validation, and safe error
    normalization.
28. Endpoint adapters MUST explicitly select direct-DTO or standard-envelope response
    decoding. The HTTP layer MUST NOT guess based on arbitrary payload fields.
29. GET/HEAD requests MAY retry network failures and HTTP 408, 429, 500, 502, 503, and 504.
    Mutations MAY retry the same conditions only when the same idempotency key and exact
    serialized body are reused.
30. Retry delay MUST honor numeric and date-form `Retry-After`; otherwise it MUST use capped
    exponential backoff with jitter and a small bounded attempt count.
31. Mutations MUST use a UUID idempotency key generated once per logical operation. An
    explicit `--idempotency-key` MUST override generation for recovery.
32. Ambiguous mutation failures MUST persist only an operation ID, idempotency key, request
    hash, method/path, timestamp, and state. The journal MUST NOT store the full prompt,
    authorization header, or response body.
33. Generic polling MUST be reusable by research and future harnesses. It MUST accept an
    injected clock, sleeper, status target, terminal classifier, transition observer,
    request timeout, overall wait timeout, and cancellation signal.
34. Polling MUST emit only meaningful state transitions, prefer a server poll hint when
    present, add jitter, and tolerate a bounded number of transient read failures.
35. Ctrl-C during watching MUST stop local polling, print the durable run identity and
    recovery command, return 130, and leave the server-side run active.
36. The root command MUST add the first-class group `vidbyte-cli research`.
37. `research start [prompt]` MUST create a new persistent thread and first run.
38. `research add <thread_id> [prompt]` MUST append a prompt to an existing thread.
39. `research resume <run_id>` MUST continue the same resumable run identity without a
    replacement prompt.
40. Start/add prompt input MUST accept exactly one of a short positional prompt,
    `--prompt-file PATH`, or explicit stdin (`--prompt -`). Ambiguous or absent input MUST
    fail before any network request.
41. Start/add MUST support size, target sources, search calls, repeatable resource kinds,
    include/exclude domains, published-after, language, idempotency, wait, wait timeout, and
    exit-status options.
42. Domain filters MUST be normalized to hostname-only lowercase values, deduplicated, and
    rejected when include/exclude sets overlap.
43. The CLI MUST NOT expose PR #284's `provider_keys` field as a raw credential or provider
    key option.
44. Mutation commands MUST return after HTTP 202 by default. `--wait` MUST compose the same
    watcher used by `research watch`.
45. `research status <run_id>` MUST return one coarse snapshot.
46. `research watch <run_id>` MUST watch until terminal status, timeout, or interrupt.
47. `research runs list`, `research threads list`, `research sources list --thread`,
    `research artifacts list --thread`, and `research artifacts get <artifact_id>` MUST use
    cursor pagination and explicit ownership-scoped IDs.
48. `research capabilities` MUST fetch server-owned sizes, limits, resource kinds, supported
    export providers, formats, and compatibility information.
49. `research export artifact <artifact_id>... --to PROVIDER`,
    `research export thread <thread_id> --to PROVIDER`, and
    `research export portfolio --to PROVIDER` MUST submit capability-validated server-side
    export jobs.
50. Export commands MUST use explicit selection; the CLI MUST never infer “current thread,”
    “all artifacts,” or a provider from local state.
51. The research CLI MUST display only coarse state and aggregate counts. It MUST NOT expose
    agent prompts, tool calls, internal provider diagnostics, or the web-only event trace.
52. Run state classification MUST live in one research domain class. Unknown server states
    MUST fail with a protocol/version error rather than poll forever.
53. `status` and list commands MUST exit 0 when retrieval succeeds regardless of remote run
    outcome. `status --exit-status`, `watch --exit-status`, and mutation `--wait
    --exit-status` MUST reflect completed/partial/failed/credit-exhausted outcomes.
54. Large artifact content MUST require an explicit output path; it MUST not be dumped to an
    interactive terminal by default.
55. The research command tree introduced in PR 6 MUST be disabled by default behind
    `VIDBYTE_EXPERIMENTAL_RESEARCH=1` until PR 7 supplies the API gateway. PR 7 MUST enable
    the complete surface by default.
56. PR 7 MUST connect to the currently visible mutation routes and the assumed read/export
    routes in Section 8, without embedding research orchestration in the CLI.
57. API errors MUST be mapped using HTTP status and stable server error code when present;
    the CLI MUST NOT branch on human `title`, `subtitle`, or `description` prose.
58. The package MUST have one canonical version source through `importlib.metadata`.
59. The repository MUST provide `python scripts/run_ci.py` as the canonical local gate.
60. CI MUST run Ruff lint, Ruff format check, strict mypy, compileall, smoke help/entrypoint
    checks, sdist/wheel build, metadata validation, and clean-wheel installation checks.

### Non-Functional Requirements

- **Performance:** Offline `--help`, `--version`, and config reads must perform no HTTP calls.
  A single CLI invocation must reuse one HTTP connection pool. Polling must not occur more
  frequently than the greater of the local policy and server-provided poll hint.
- **Scalability:** List commands use opaque cursors rather than page numbers. `--all` is not
  included initially; callers must opt through cursor/limit boundaries.
- **Security:** Secrets and full prompts are excluded from logs, errors, journals, config,
  telemetry, and human/machine diagnostic output. Non-local API URLs require HTTPS.
  `localhost`, `127.0.0.1`, and `::1` may use HTTP for development.
- **Privacy:** Debug mode may show configuration provenance, request method/path, status,
  request ID, retry attempt, and timing, but never authorization headers, API keys, prompt
  content, provider credentials, artifact content, or raw server bodies.
- **Accessibility:** Output uses text labels in addition to symbols or color. Non-TTY and
  screen-reader-friendly output is append-only and avoids cursor control.
- **Reliability:** Retried mutations reuse byte-identical bodies and keys. Timeouts and
  interrupts never imply remote cancellation. Invalid/unknown response schemas fail closed.
- **Portability:** Supported runtime is Python 3.11+. CI covers Linux, Windows, and macOS and
  representative supported Python versions.
- **Maintainability:** `lib/` contains cross-feature mechanisms only;
  `features/research/` owns all research vocabulary and policy. Generic layers may not
  import research modules.
- **Observability:** Request IDs, operation IDs, status transitions, retry decisions, and
  elapsed time are available under safe debug output. No telemetry is added.
- **Code style:** Non-trivial behavior is class-first. Every new or modified function/method
  signature fits on one line and has an immediate 1-2 line explanatory comment. Nested Click
  callbacks are allowed only as trivial adapters into command classes.
- **Verification constraint:** No new feature test files are added. This increases regression
  risk, so the smoke, type, lint, package, and cross-platform CI gates are release blockers.

---

## 5. High-Level Design

The existing repository layout is retained rather than mechanically moving accepted modules.
`commands/` remains the adapter layer for stable platform commands, `lib/` remains the
reusable mechanism layer, `lib/harness/` and `harnesses/` retain their accepted dynamic
harness roles, and a new `features/` root owns feature-specific vertical slices. Research
gets `domain`, `application`, `commands`, `presentation`, and `infrastructure` subpackages.
The central dependency rule is one-way: application bootstrap may import everything;
features may import shared `lib` mechanisms; shared `lib` mechanisms may not import a
feature.

`CliApplication` becomes the only program runner. It resolves global options into an
invocation-owned `ApplicationContext`, registers static commands synchronously, lazily
attaches dynamic manifest harnesses when requested, and delegates all failures to one error
handler. `IOStreams` and `OutputManager` enforce the stdout/stderr contract. Config,
credentials, HTTP clients, endpoint groups, pollers, and research services are lazy so help
construction has no side effects.

The research feature is built against a `ResearchGateway` protocol. PRs 5 and 6 implement
domain validation, use cases, watching, presenters, and Click adapters using an unavailable
gateway and an off-by-default feature flag. PR 7 implements `ApiResearchGateway`, selects
direct-DTO response decoding for research, wires it into `ApplicationContext`, enables the
command group, and removes the unavailable execution path.

```text
console shim
    |
    v
CliApplication -------> ApplicationContext (lazy invocation services)
    |                              |
    |                              +--> config / credentials / IO / output
    |                              +--> ApiClient / retry / idempotency journal
    |                              +--> Poller / clock / signal controller
    |
    +--> existing platform commands
    +--> existing dynamic harness runtime
    +--> research command adapters
             |
             v
       ResearchService -----> ResearchGateway protocol
             |                         |
             +--> ResearchWatcher      +--> ApiResearchGateway (PR 7)
             +--> ResearchPresenter            |
                                               v
                                         Vidbyte API
```

### Seven-PR dependency graph

```text
PR 1  Python application + packaging/CI baseline
  |
PR 2  IO, output, terminal, and typed error contracts
  |
PR 3  Config, profiles, path migration, and secure credentials
  |
PR 4  HTTP, retries, idempotency, polling, and generic harness plumbing
  |
PR 5  Research domain + application ports/use cases
  |
PR 6  Research command tree + presentation (feature-gated)
  |
PR 7  Research API gateway + production wiring
```

---

## 6. Detailed Design

### 6.1 PR 1 - Python Application, Packaging, and CI Baseline

**File(s):** `pyproject.toml`, `.github/workflows/ci.yml`, `scripts/run_ci.py`,
`scripts/smoke.py`, `src/vidbyte_cli/cli.py`, `src/vidbyte_cli/__main__.py`,
`src/vidbyte_cli/lib/runtime/application.py`,
`src/vidbyte_cli/lib/runtime/context.py`,
`src/vidbyte_cli/lib/runtime/version.py`,
`src/vidbyte_cli/lib/io/streams.py`, documentation files
**Type:** New + Modified

#### What it does

Creates a testable application kernel, one version source, invocation-scoped service
composition, injected streams, and canonical local/remote quality gates. It does not
implement research or network behavior.

#### Interface / API

```python
class CliApplication:
    def run(self, argv: list[str]) -> int:
        # Builds one invocation, dispatches Click without standalone exits, and returns a code.

class ApplicationContext:
    def close(self) -> None:
        # Closes any lazy resources created during this invocation.

class ApplicationContextFactory:
    def create(self, options: GlobalOptions, streams: IOStreams) -> ApplicationContext:
        # Resolves invocation-owned collaborators without performing credential or network I/O.

class VersionProvider:
    def current(self) -> str:
        # Returns installed package metadata or a safe development fallback.

@dataclass(frozen=True)
class IOStreams:
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO
```

#### Logic / Algorithm

1. `__main__.py` calls `main()`, and the console shim converts the returned code to
   `SystemExit`.
2. `CliApplication.run` creates streams and a Click root, registers commands, and invokes
   `standalone_mode=False`.
3. Parsed global options are converted into immutable `GlobalOptions`.
4. `ApplicationContextFactory` creates lazy service factories and attaches the context to
   Click's invocation object.
5. `finally` closes only services that were actually created.
6. `scripts/run_ci.py` runs the canonical gates in a temporary build directory.
7. GitHub Actions runs the same script on supported OS/Python combinations.

#### Edge Cases & Error Handling

- Missing installed metadata during editable source execution returns `0.1.0.dev0` rather
  than duplicating a literal release version.
- Help/version paths never force construction of credentials or HTTP clients.
- A cleanup failure is recorded under debug output but does not replace a more important
  command failure.
- The local stale branch is not used as an implementation base; the worktree is created
  directly from a freshly verified `origin/main`.

### 6.2 PR 2 - IO, Output, Terminal, and Error Contracts

**File(s):** `src/vidbyte_cli/lib/io/terminal.py`,
`src/vidbyte_cli/lib/io/prompt.py`,
`src/vidbyte_cli/lib/output/formats.py`,
`src/vidbyte_cli/lib/output/models.py`,
`src/vidbyte_cli/lib/output/manager.py`,
`src/vidbyte_cli/lib/errors/codes.py`,
`src/vidbyte_cli/lib/errors/failures.py`,
`src/vidbyte_cli/lib/errors/handler.py`,
`src/vidbyte_cli/lib/runtime/options.py`, existing logger/renderer/error/bootstrap files
**Type:** New + Modified

#### What it does

Establishes one output API for human, JSON, JSONL, progress, warning, and error rendering;
one terminal-capability detector; one prompt-input resolver; and one typed error-to-exit
boundary.

#### Interface / API

```python
class OutputFormat(str, Enum):
    HUMAN = "human"
    JSON = "json"
    JSONL = "jsonl"
    NONE = "none"

class CliErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"
    API_UNAVAILABLE = "API_UNAVAILABLE"
    API_PROTOCOL_ERROR = "API_PROTOCOL_ERROR"
    INTERRUPTED = "INTERRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

class CliError(Exception):
    def __init__(self, code: CliErrorCode, message: str, exit_code: int = 1, *, hint: str | None = None, retryable: bool = False, request_id: str | None = None, cause: Exception | None = None) -> None:
        # Captures stable machine semantics and safe human recovery information.

class OutputManager:
    def result(self, document: OutputDocument, human: str) -> None:
        # Writes a successful result to stdout in the selected format.

    def transition(self, document: OutputDocument, human: str) -> None:
        # Writes coarse progress to stderr or JSONL according to terminal/output mode.

    def error(self, error: CliError) -> None:
        # Writes a safe structured or human error to stderr.

class PromptInputResolver:
    def resolve(self, positional: str | None, prompt_file: str | None) -> str:
        # Resolves exactly one positional, file, or explicit-stdin prompt source.
```

#### Logic / Algorithm

1. Root flags are parsed before service construction.
2. `TerminalCapabilities` inspects TTY state, `NO_COLOR`, `TERM`, color preference, and
   `--no-input`.
3. `OutputManager.result` writes one stdout document for JSON or one human block.
4. `OutputManager.transition` keeps progress off stdout; JSONL is the only format that
   streams result records.
5. `ErrorHandler` maps `CliError`, Click usage errors, aborts, and unexpected errors to the
   documented exit table.
6. `PromptInputResolver` checks source exclusivity and reads UTF-8 with a 20,000-character
   safety bound for research-compatible use.

#### Edge Cases & Error Handling

- Broken pipe is treated as a normal downstream consumer closure rather than an internal
  stack trace.
- Invalid Unicode or oversized prompt files produce usage errors before service calls.
- JSON serialization failure is an internal software error and never falls back to a
  misleading human success message.
- `--json` and a conflicting `--format` value produce a usage error.
- Noninteractive input never triggers a prompt.

### 6.3 PR 3 - Configuration, Profiles, Paths, and Credentials

**File(s):** `src/vidbyte_cli/lib/config/models.py`,
`src/vidbyte_cli/lib/config/resolver.py`,
`src/vidbyte_cli/lib/config/migration.py`,
`src/vidbyte_cli/lib/config/atomic.py`,
`src/vidbyte_cli/lib/auth/resolver.py`,
`src/vidbyte_cli/lib/auth/keyring_store.py`,
`src/vidbyte_cli/lib/auth/input.py`,
`src/vidbyte_cli/lib/auth/verifier.py`, existing config/auth commands and stores,
runtime composition/options, harness credential/path adapter, smoke checks,
`pyproject.toml`, `.env.example`, README and architecture documentation
**Type:** New + Modified

#### What it does

Implements typed profiles, explicit configuration provenance, platform-native paths,
legacy-path compatibility, OS keyring storage, safe fallback credentials, atomic writes,
and config/login/logout command behavior that does not yet require research.

#### Interface / API

```python
class ProfileConfig(BaseModel):
    api_url: str = "https://api.vidbyte.ai"
    output_format: OutputFormat = OutputFormat.HUMAN
    color: ColorMode = ColorMode.AUTO
    request_timeout_seconds: float = 30.0

class ConfigDocument(BaseModel):
    schema_version: Literal[1] = 1
    active_profile: str = "default"
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

class ConfigResolver:
    def resolve(self, options: GlobalOptions, environment: Mapping[str, str]) -> ResolvedConfig:
        # Applies the documented precedence and records each value's provenance.

class CredentialResolver:
    def resolve(self, profile: str, api_url: str) -> ResolvedCredential | None:
        # Resolves environment, keyring, then warned file fallback without logging values.

class CredentialStore:
    def write(self, credentials: Credentials, profile: str, api_url: str) -> None:
        # Stores a verified credential in keyring or the explicit restricted fallback.

class StateMigration:
    def migrate_if_needed(self) -> MigrationResult:
        # Copies and verifies legacy state without deleting the source.
```

#### Logic / Algorithm

1. `VidbytePaths` uses `platformdirs` for config, cache, state, and data roots.
2. Read resolution checks platform-native files, then legacy `~/.vidbyte`.
3. Migration copies config and manifest cache through atomic writes and verifies parse/hash.
4. Credential migration writes the keyring first; only a successful read-back marks it
   migrated.
5. `CredentialResolver` checks `VIDBYTE_API_KEY` before any local store.
6. Keyring entries use service `vidbyte-cli` and account `<profile>@<normalized-api-host>`.
7. If no viable keyring exists, login asks for explicit confirmation before using a
   permission-restricted file and emits a warning.
8. Config commands operate on an allow-list of profile fields and expose provenance under
   debug mode.

#### Edge Cases & Error Handling

- Invalid or future config schema versions fail with a recovery hint and preserve the file.
- Symlinked credential/config targets are rejected for writes.
- Concurrent writes use an atomic replace and detect incompatible schema changes.
- Keyring initialization/set/delete failures are translated without leaking the token.
- HTTP API URLs are allowed only for loopback development hosts.
- Environment credentials are never persisted implicitly.

### 6.4 PR 4 - HTTP, Retry, Idempotency, Polling, and Generic Harness Plumbing

**File(s):** `src/vidbyte_cli/lib/api/retry.py`,
`src/vidbyte_cli/lib/api/problem.py`,
`src/vidbyte_cli/lib/api/response.py`,
`src/vidbyte_cli/lib/polling/`,
`src/vidbyte_cli/lib/operations/`,
`src/vidbyte_cli/lib/runtime/clock.py`,
`src/vidbyte_cli/lib/runtime/signals.py`, existing API, auth, git, harness, renderer, and
command files
**Type:** New + Modified

#### What it does

Implements the reusable network and long-running-operation platform. It completes generic
auth/harness endpoint plumbing, manifest caching, repo inspection, run presentation, safe
retries, idempotency recovery records, signal-aware polling, and coarse progress.

#### Interface / API

```python
class RetryPolicy:
    def decide(self, request: RequestMetadata, attempt: int, response: httpx.Response | None, error: Exception | None) -> RetryDecision:
        # Returns retry/no-retry and a bounded delay for one transport outcome.

class ApiClient:
    def request(self, method: str, path: str, *, body: BaseModel | None, response_model: type[TModel], response_shape: ResponseShape, idempotency_key: str | None = None, signal: CancellationSignal | None = None) -> TModel:
        # Executes one typed request through timeout, retry, decoding, and redaction policies.

class IdempotencyKeyFactory:
    def create(self, explicit: str | None) -> str:
        # Validates an explicit key or creates one UUID for the logical mutation.

class OperationJournal:
    def begin(self, record: PendingOperation) -> None:
        # Persists a prompt-free recovery record before a costly mutation is sent.

    def accepted(self, operation_id: str, remote_id: str) -> None:
        # Marks an operation accepted after a durable server identity is received.

class PollTarget(Protocol[TModel]):
    def fetch(self) -> TModel:
        # Fetches one current remote snapshot.

    def is_terminal(self, value: TModel) -> bool:
        # Classifies whether the snapshot ends the local watch.

    def fingerprint(self, value: TModel) -> str:
        # Returns a stable transition fingerprint for duplicate suppression.

class Poller(Generic[TModel]):
    def watch(self, target: PollTarget[TModel], observer: PollObserver[TModel], options: PollOptions) -> PollResult[TModel]:
        # Polls with hints/backoff until terminal, timeout, or cancellation.
```

#### Logic / Algorithm

1. `ApiClient` validates relative paths and constructs one request with redacted metadata.
2. The same serialized body, idempotency key, and request identity are retained across
   mutation attempts.
3. The decoder checks content type and response size, then validates direct DTO or envelope
   according to the endpoint adapter.
4. Error decoding prefers a stable code; absent a code, it maps the HTTP status without
   parsing prose.
5. The operation journal is written before a mutation and updated after admission.
6. The generic `Poller` uses server hint, local policy, jitter, and an injected sleeper.
7. Signal handling sets cancellation state; it does not call remote cancellation.
8. Existing generic harness waiting delegates to `Poller`.
9. Existing auth, config, doctor, generic harness, catalog-cache, and repo-inspection stubs
   are completed where their backend contracts already exist in the scaffold.

#### Edge Cases & Error Handling

- 204 with an expected body, invalid JSON, wrong content type, oversized body, missing
  envelope data, and Pydantic validation failures become protocol errors.
- POST without an idempotency key is never retried.
- `Retry-After` beyond the local cap is clamped and reported under debug output.
- An interrupted or timed-out wait leaves its accepted operation record and prints a
  recovery command.
- Manifest cache corruption is quarantined and followed by a network refresh; offline
  callers receive a clear stale/missing-cache error.
- A dirty repository is reported explicitly; commands choose whether it is allowed rather
  than silently submitting an ambiguous ref.

### 6.5 PR 5 - Research Domain and Application Layer

**File(s):** `src/vidbyte_cli/features/research/domain/`,
`src/vidbyte_cli/features/research/application/`
**Type:** New files

#### What it does

Introduces research-owned vocabulary, validation, gateway ports, use cases, status
classification, and generic-watcher adaptation. It contains no Click and no HTTPX.

#### Interface / API

```python
class ResearchStatus(str, Enum):
    ADMITTING = "admitting"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CREDIT_EXHAUSTED = "credit_exhausted"

class ResearchGateway(Protocol):
    def start(self, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted:
        # Creates a new persistent research thread and first run.

    def add(self, thread_id: str, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted:
        # Appends a prompt as a new run in an owned thread.

    def resume(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted:
        # Continues an owned terminal-resumable run under the same run identity.

    def get_run(self, run_id: str) -> ResearchRun:
        # Returns one ownership-scoped run snapshot.

class ResearchService:
    def start(self, command: ResearchMutationInput) -> ResearchMutationResult:
        # Validates input, submits an idempotent run, and optionally composes watching.

    def add(self, thread_id: str, command: ResearchMutationInput) -> ResearchMutationResult:
        # Appends a validated research request and optionally composes watching.

    def resume(self, run_id: str, command: ResearchResumeInput) -> ResearchMutationResult:
        # Resumes a run and optionally composes watching.

class ResearchStatePolicy:
    def is_terminal(self, status: ResearchStatus) -> bool:
        # Classifies the known wire states without duplicating policy in commands.

    def exit_code(self, status: ResearchStatus) -> int:
        # Maps a terminal outcome to the documented optional exit-status contract.
```

#### Logic / Algorithm

1. Pydantic request models mirror PR #284's strict constraints and forbid extra fields.
2. Domain normalization strips/deduplicates domains and validates ISO calendar dates.
3. A service accepts domain inputs and a gateway protocol, not Click parameters or raw
   dictionaries.
4. Mutations create/reuse one idempotency key and operation journal entry.
5. Optional waiting delegates to `ResearchWatcher`, which adapts `ResearchGateway.get_run`
   to the generic `Poller`.
6. Page/resource/export use cases remain capability- and cursor-driven.

#### Edge Cases & Error Handling

- Empty/oversized prompts, invalid counts, invalid language/date/domain values, and
  contradictory filters fail locally.
- Unknown statuses fail with `API_PROTOCOL_ERROR`.
- Resume sends no prompt and does not let the client override the original request.
- Resource and export identifiers are opaque strings and are never parsed or inferred.
- Capability validation does not replace server validation; it only improves local errors.

### 6.6 PR 6 - Research Commands and Presentation

**File(s):** `src/vidbyte_cli/features/research/commands/`,
`src/vidbyte_cli/features/research/presentation/`,
`src/vidbyte_cli/commands/__init__.py`, bootstrap and documentation files
**Type:** New + Modified

#### What it does

Builds the complete top-level Click command tree and human/machine presenters against the
research application interfaces. Execution stays disabled by default until PR 7 supplies
the HTTP adapter.

#### Interface / API

```text
vidbyte-cli research start [prompt]
vidbyte-cli research add <thread_id> [prompt]
vidbyte-cli research resume <run_id>
vidbyte-cli research status <run_id>
vidbyte-cli research watch <run_id>
vidbyte-cli research runs list
vidbyte-cli research threads list
vidbyte-cli research sources list --thread <thread_id>
vidbyte-cli research artifacts list --thread <thread_id>
vidbyte-cli research artifacts get <artifact_id>
vidbyte-cli research capabilities
vidbyte-cli research export artifact <artifact_id>... --to <provider>
vidbyte-cli research export thread <thread_id> --to <provider>
vidbyte-cli research export portfolio --to <provider>
```

```python
class ResearchCommandRegistrar:
    def register(self, parent: click.Group, context: ApplicationContext) -> None:
        # Attaches the feature-owned group without creating its gateway.

class ResearchPresenter:
    def run(self, value: ResearchRun) -> PresentedResult:
        # Produces stable machine data and concise human run output.

    def artifact(self, value: ResearchArtifact, output_path: Path | None) -> PresentedResult:
        # Renders metadata or writes explicitly requested large content safely.
```

#### Logic / Algorithm

1. The registrar creates nested groups synchronously.
2. Each command class owns Click declarations, parses into a Pydantic command input, calls
   `ApplicationContext.research_service()` only inside execution, and presents the result.
3. Repeated options use Click callbacks that append values without global mutable state.
4. `--wait` delegates to the service; commands do not implement loops.
5. Presenters generate both stable `OutputDocument` data and concise human text.
6. The root registrar checks `VIDBYTE_EXPERIMENTAL_RESEARCH`; PR 6 defaults it off and the
   smoke gate enables it only for help-tree construction.

#### Edge Cases & Error Handling

- Prompt source ambiguity is a usage error.
- Non-TTY commands do not prompt.
- `artifact get` refuses to print large content without an explicit file.
- Multiple artifact export requires at least one ID and preserves input order.
- Provider/format choices are validated against server capabilities when available.
- No command emits the detailed research agent event log.

### 6.7 PR 7 - Vidbyte Research API Gateway and Production Wiring

**File(s):** `src/vidbyte_cli/features/research/infrastructure/api_gateway.py`,
`src/vidbyte_cli/features/research/infrastructure/__init__.py`, research application/domain,
runtime context, registration, smoke, and documentation files
**Type:** New + Modified

#### What it does

Implements the final HTTP adapter, direct DTO decoding, pagination, export job submission,
and application-context wiring. It enables the research group by default.

#### Interface / API

```python
class ApiResearchGateway(ResearchGateway):
    def __init__(self, client: ApiClient) -> None:
        # Binds research use cases to the API-key public research surface.

    def start(self, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted:
        # POSTs the exact PR #284 create DTO with a stable idempotency key.

    def add(self, thread_id: str, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted:
        # POSTs another prompt into an existing thread.

    def resume(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted:
        # POSTs an empty continuation body while preserving the run identity.
```

#### Logic / Algorithm

1. `ApplicationContext.research_service()` lazily constructs `ApiResearchGateway`.
2. Mutation methods use direct DTO response decoding and preserve one idempotency key.
3. Read methods validate direct resource/page DTOs.
4. Export methods fetch capabilities, validate provider/format, submit a server job, and
   optionally use the generic watcher.
5. The experimental registration gate becomes enabled by default; an environment kill
   switch may remain for rollback.
6. Smoke checks build the entire research help tree and exercise offline command parsing
   without hitting the real API.

#### Edge Cases & Error Handling

- Current PR #284 errors without a stable code are mapped by status only; human prose is
  displayed but never parsed.
- Missing assumed read/export routes produce a clear capability/API-version error, not a
  fallback to browser-only server actions.
- Cursor values are passed through as opaque URL query values.
- Ownership failures are not distinguished from missing resources beyond the safe server
  response.
- A CLI/API minimum-version mismatch instructs the user to upgrade rather than silently
  dropping fields.

### 6.8 Code-Style Application

**File(s):** Every new or modified Python source file
**Type:** New + Modified

#### What it does

Applies the selected skill's mandatory class-first, one-line-signature, immediate-comment
style to every touched function and method.

#### Interface / API

```python
class ExampleService:
    def execute(self, request: ExampleRequest) -> ExampleResult:
        # Validates the request, performs the use case, and returns a typed result.
```

#### Logic / Algorithm

1. Non-trivial module-level helpers become collaborators or private class methods.
2. Click's nested callback remains a two-line adapter that delegates to its command class.
3. Every touched function/method signature is one physical line.
4. The next one or two lines explain the responsibility, not the syntax.
5. Inline comments are limited to non-obvious invariants, security boundaries, or
   compatibility behavior.

#### Edge Cases & Error Handling

- Existing untouched files are not mechanically rewritten solely for style.
- A touched file is brought fully into compliance rather than mixing styles within it.

---

## 7. Data Model Changes

### 7.1 ConfigDocument

**Change type:** Modified local schema

```python
class ConfigDocument(BaseModel):
    schema_version: Literal[1] = 1
    active_profile: str = "default"
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
```

**Migration strategy:**

- Forward migration: recognize the current flat `config.json`, map known keys into the
  default profile, write the new platform-native file atomically, verify it, and retain the
  original legacy file.
- Rollback plan: previous versions continue reading `~/.vidbyte/config.json`; the legacy
  source is not deleted. The new config can be ignored safely by an older CLI.

### 7.2 CredentialRecord

**Change type:** Modified local storage model

```python
class CredentialRecord(BaseModel):
    schema_version: Literal[1] = 1
    profile: str
    api_host: str
    api_key: SecretStr
```

**Migration strategy:**

- Forward migration: write keyring entry, read it back, then mark migration complete in
  non-secret state. If no viable backend exists, retain a mode-restricted JSON fallback
  after explicit warning.
- Rollback plan: never delete the legacy credential during this program. Logout clears all
  known locations idempotently.

### 7.3 PendingOperation

**Change type:** New local state model

```python
class PendingOperation(BaseModel):
    schema_version: Literal[1] = 1
    operation_id: str
    idempotency_key: str
    method: str
    path: str
    request_sha256: str
    state: Literal["pending", "accepted", "ambiguous", "completed"]
    remote_id: str | None = None
    created_at: datetime
    updated_at: datetime
```

**Migration strategy:**

- Forward migration: N/A - new state directory; records contain no full request.
- Rollback plan: safe to ignore or delete because server idempotency remains authoritative.

### 7.4 Research Domain Models

**Change type:** New CLI-only wire/domain models

```python
class ResearchRunRequest(BaseModel):
    prompt: str
    request_schema_version: Literal[1] = 1
    size: ResearchSize = ResearchSize.SMALL
    target_sources: int | None = Field(default=None, ge=1, le=1000)
    search_calls: int | None = Field(default=None, ge=1, le=100)
    resource_kinds: list[ResearchKind] = Field(
        default_factory=lambda: [ResearchKind.PAPER, ResearchKind.WEB]
    )
    include_domains: list[str] = Field(default_factory=list, max_length=50)
    exclude_domains: list[str] = Field(default_factory=list, max_length=50)
    published_after: date | None = None
    language: str = Field(default="en", min_length=2, max_length=12)


class ResearchRunAccepted(BaseModel):
    thread_id: str
    run_id: str
    status: ResearchStatus


class CursorPage(BaseModel, Generic[TModel]):
    items: list[TModel]
    next_cursor: str | None = None
```

Additional models: `ResearchRun`, `ResearchThread`, `ResearchSource`,
`ResearchArtifact`, `ResearchCapabilities`, `ResearchExportRequest`,
`ResearchExportJob`, `ResearchProgress`, and `ResearchUsage`.

**Migration strategy:**

- Forward migration: N/A - no local research persistence.
- Rollback plan: remove/disable the command surface; backend data is unaffected.

---

## 8. API Changes

This repository does not implement backend endpoints. The entries below are the public
API-key contracts consumed by PR 7. The first three exist in PR #284; the remaining routes
are explicit assumptions required by the user's “assume the API is fully implemented”
instruction.

### 8.1 POST /research/run

**Change type:** Existing backend route, new CLI consumer

**Request:**

```json
{
  "prompt": "string, 1-20000 characters",
  "request_schema_version": 1,
  "size": "small | medium | large",
  "target_sources": "integer 1-1000 or null",
  "search_calls": "integer 1-100 or null",
  "resource_kinds": ["paper", "web"],
  "include_domains": ["hostname"],
  "exclude_domains": ["hostname"],
  "published_after": "YYYY-MM-DD or null",
  "language": "2-12 character language code"
}
```

Header: `Idempotency-Key` is required.

**Response:**

```json
{
  "thread_id": "rth_...",
  "run_id": "run_...",
  "status": "accepted"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 400/422 | Invalid request or contradictory filters |
| 401 | Missing/invalid API key |
| 402 | Insufficient credits |
| 409 | Idempotency or admission conflict |
| 429 | Rate limited |
| 5xx | Temporary/internal admission failure |

### 8.2 POST /research/threads/{thread_id}/run

**Change type:** Existing backend route, new CLI consumer

**Request:** Same as Section 8.1.

**Response:** Same accepted DTO as Section 8.1, retaining the requested thread ID.

**Error cases:**

| Status | Condition |
|--------|-----------|
| 404 | Thread absent or not owned |
| 409 | Thread/idempotency conflict |
| Other | Same as Section 8.1 |

### 8.3 POST /research/runs/{run_id}/continue

**Change type:** Existing backend route, new CLI consumer

**Request:**

```json
{}
```

Header: `Idempotency-Key` is required.

**Response:** Same accepted DTO, preserving the run identity.

**Error cases:**

| Status | Condition |
|--------|-----------|
| 404 | Run absent or not owned |
| 409 | Run not terminal-resumable or changed during continuation |
| 402 | Insufficient credits for continuation |

### 8.4 GET /research/runs/{run_id}

**Change type:** Assumed new public API route

**Request:** Path ID only.

**Response:**

```json
{
  "thread_id": "rth_...",
  "run_id": "run_...",
  "status": "running",
  "phase": "discovery",
  "terminal": false,
  "resumable": false,
  "poll_after_ms": 5000,
  "progress": {
    "target_sources": 50,
    "sources_discovered": 21,
    "artifacts_completed": 8
  },
  "usage": {
    "cost_cents": "decimal string",
    "model_tokens": 0,
    "search_calls": 0,
    "fetch_calls": 0
  },
  "disclaimer": null,
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 404 | Run absent or not owned |
| 410 | Run metadata no longer retained |
| 426 | CLI/API version incompatible |

### 8.5 GET /research/runs

**Change type:** Assumed new public API route

**Request:** `cursor`, `limit`, and optional `thread_id`.

**Response:**

```json
{
  "items": ["ResearchRun summary objects"],
  "next_cursor": "opaque string or null"
}
```

**Error cases:** 400 invalid cursor/limit, 401 auth, 404 owned thread filter missing.

### 8.6 GET /research/threads

**Change type:** Assumed new public API route

**Request:** `cursor`, `limit`.

**Response:**

```json
{
  "items": [
    {
      "thread_id": "rth_...",
      "title": "string or null",
      "latest_run_id": "run_...",
      "latest_status": "running",
      "source_count": 21,
      "artifact_count": 8,
      "created_at": "ISO-8601",
      "updated_at": "ISO-8601"
    }
  ],
  "next_cursor": null
}
```

**Error cases:** 400 invalid cursor/limit, 401 auth.

### 8.7 GET /research/threads/{thread_id}/sources

**Change type:** Assumed new public API route

**Request:** `cursor`, `limit`.

**Response:**

```json
{
  "items": [
    {
      "source_id": "src_...",
      "url": "https://...",
      "title": "string",
      "resource_kind": "paper",
      "status": "completed",
      "discovered_at": "ISO-8601"
    }
  ],
  "next_cursor": null
}
```

**Error cases:** 404 thread absent/not owned, 400 invalid cursor/limit.

### 8.8 GET /research/threads/{thread_id}/artifacts

**Change type:** Assumed new public API route

**Request:** `cursor`, `limit`.

**Response:**

```json
{
  "items": [
    {
      "artifact_id": "art_...",
      "source_id": "src_...",
      "title": "string",
      "summary": "string",
      "relevance": "string",
      "recommendations": ["string"],
      "created_at": "ISO-8601"
    }
  ],
  "next_cursor": null
}
```

**Error cases:** 404 thread absent/not owned, 400 invalid cursor/limit.

### 8.9 GET /research/artifacts/{artifact_id}

**Change type:** Assumed new public API route

**Request:** Path ID only; optional content inclusion must be an explicit query.

**Response:**

```json
{
  "artifact_id": "art_...",
  "thread_id": "rth_...",
  "source_id": "src_...",
  "title": "string",
  "summary": "string",
  "relevance": "string",
  "recommendations": ["string"],
  "source_url": "https://...",
  "content": "optional large content"
}
```

**Error cases:** 404 artifact absent/not owned, 413 content too large for inline response.

### 8.10 GET /research/capabilities

**Change type:** Assumed new public API route

**Request:** None.

**Response:**

```json
{
  "request_schema_versions": [1],
  "sizes": ["small", "medium", "large"],
  "resource_kinds": ["paper", "web"],
  "limits": {
    "max_target_sources": 1000,
    "max_search_calls": 100,
    "max_domains": 50
  },
  "export_providers": [
    {
      "id": "notion",
      "scopes": ["artifact", "thread", "portfolio"],
      "formats": ["notion_page"]
    }
  ],
  "min_cli_version": "0.1.0"
}
```

**Error cases:** 401 auth if capabilities are account-specific, 426 incompatible CLI.

### 8.11 POST /research/exports

**Change type:** Assumed new public API route

**Request:**

```json
{
  "scope": "artifact | thread | portfolio",
  "artifact_ids": ["art_..."],
  "thread_id": "rth_... or null",
  "provider": "capability provider id",
  "format": "capability format id or null"
}
```

Header: `Idempotency-Key` is required.

**Response:**

```json
{
  "export_id": "exp_...",
  "status": "accepted",
  "poll_after_ms": 2000
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 400/422 | Invalid scope/selection/provider/format |
| 401/403 | Auth or integration not connected |
| 404 | Selected resource absent/not owned |
| 409 | Idempotency or export conflict |

### 8.12 GET /research/exports/{export_id}

**Change type:** Assumed new public API route

**Request:** Path ID only.

**Response:**

```json
{
  "export_id": "exp_...",
  "status": "running | completed | failed",
  "destination_url": "https://... or null",
  "poll_after_ms": 2000
}
```

**Error cases:** 404 export absent/not owned, 410 result expired.

---

## 9. File Change Manifest

The `PR` column assigns each path to its first/create PR and lists later PRs that may refine
the same existing file. No source file is deleted in this program.

| Action | PR | File Path | Reason |
|--------|----|-----------|--------|
| CREATE | 1 | `docs/design/python-cli-research-harness-program.md` | Source of truth for the seven-PR program |
| CREATE | 1 | `.github/workflows/ci.yml` | Cross-platform Python quality/package gate |
| CREATE | 1 | `scripts/README.md` | Verification-script ownership, file index, non-goals, and decision log |
| CREATE | 1 | `scripts/run_ci.py` | Canonical local CI orchestrator |
| CREATE | 1 | `src/vidbyte_cli/README.md` | Package boundary, routing index, non-goals, and decision log |
| CREATE | 1 | `src/vidbyte_cli/lib/README.md` | Reusable CLI platform boundary and routing index |
| CREATE | 1 | `src/vidbyte_cli/lib/runtime/README.md` | Runtime ownership, file index, non-goals, and decision log |
| CREATE | 1 | `src/vidbyte_cli/lib/runtime/__init__.py` | Runtime package boundary |
| CREATE | 1 | `src/vidbyte_cli/lib/runtime/application.py` | Testable `CliApplication` runner |
| CREATE | 1 | `src/vidbyte_cli/lib/runtime/context.py` | Lazy invocation-owned dependency context |
| CREATE | 1 | `src/vidbyte_cli/lib/runtime/version.py` | Single package-version provider |
| CREATE | 1 | `src/vidbyte_cli/lib/io/README.md` | IO ownership, file index, non-goals, and decision log |
| CREATE | 1 | `src/vidbyte_cli/lib/io/__init__.py` | IO package boundary |
| CREATE | 1 | `src/vidbyte_cli/lib/io/streams.py` | Injected stdin/stdout/stderr model |
| CREATE | 1 | `src/vidbyte_cli/lib/harness/README.md` | Generic harness ownership, file index, non-goals, and decision log |
| CREATE | 2 | `src/vidbyte_cli/lib/io/terminal.py` | TTY/color/cursor capability detection |
| CREATE | 2 | `src/vidbyte_cli/lib/io/prompt.py` | Exclusive positional/file/stdin prompt resolution |
| CREATE | 2 | `src/vidbyte_cli/lib/output/README.md` | Output ownership, file index, non-goals, and decision log |
| CREATE | 2 | `src/vidbyte_cli/lib/output/formats.py` | Output/color enumerations |
| CREATE | 2 | `src/vidbyte_cli/lib/output/models.py` | Versioned machine output documents |
| CREATE | 2 | `src/vidbyte_cli/lib/output/manager.py` | Stdout/stderr and format policy |
| CREATE | 2 | `src/vidbyte_cli/lib/errors/README.md` | Error ownership, file index, non-goals, and decision log |
| CREATE | 2 | `src/vidbyte_cli/lib/errors/codes.py` | Stable error and exit-code vocabulary |
| CREATE | 2 | `src/vidbyte_cli/lib/errors/failures.py` | One CliError subclass per platform failure, with agent-native prose |
| CREATE | 2 | `src/vidbyte_cli/lib/errors/handler.py` | Central exception rendering/mapping |
| CREATE | 2 | `src/vidbyte_cli/lib/runtime/options.py` | Service-free root-option preflight and typed callback values |
| CREATE | 3 | `src/vidbyte_cli/lib/config/README.md` | Configuration ownership, file index, non-goals, and decision log |
| CREATE | 3 | `src/vidbyte_cli/lib/config/models.py` | Typed profiles and config schema |
| CREATE | 3 | `src/vidbyte_cli/lib/config/resolver.py` | Precedence and provenance resolution |
| CREATE | 3 | `src/vidbyte_cli/lib/config/migration.py` | Copy/verify legacy-state migration |
| CREATE | 3 | `src/vidbyte_cli/lib/auth/README.md` | Credential ownership, file index, non-goals, and decision log |
| CREATE | 3 | `src/vidbyte_cli/lib/auth/resolver.py` | Environment/keyring/fallback credential precedence |
| CREATE | 3 | `src/vidbyte_cli/lib/auth/keyring_store.py` | OS credential-store adapter |
| CREATE | 4 | `src/vidbyte_cli/lib/api/README.md` | HTTP boundary ownership, file index, non-goals, and decision log |
| CREATE | 4 | `src/vidbyte_cli/lib/api/retry.py` | HTTP retry classification/backoff |
| CREATE | 4 | `src/vidbyte_cli/lib/api/problem.py` | Safe server-error decoding |
| CREATE | 4 | `src/vidbyte_cli/lib/api/response.py` | Direct/envelope typed response decoding |
| CREATE | 4 | `src/vidbyte_cli/lib/polling/README.md` | Polling ownership, file index, non-goals, and decision log |
| CREATE | 4 | `src/vidbyte_cli/lib/polling/__init__.py` | Polling package exports |
| CREATE | 4 | `src/vidbyte_cli/lib/polling/policy.py` | Generic poll delay/error policy |
| CREATE | 4 | `src/vidbyte_cli/lib/polling/poller.py` | Signal-aware generic watcher |
| CREATE | 4 | `src/vidbyte_cli/lib/operations/README.md` | Operation-safety ownership, file index, non-goals, and decision log |
| CREATE | 4 | `src/vidbyte_cli/lib/operations/__init__.py` | Operation package exports |
| CREATE | 4 | `src/vidbyte_cli/lib/operations/idempotency.py` | Key generation and request hashing |
| CREATE | 4 | `src/vidbyte_cli/lib/operations/journal.py` | Prompt-free ambiguous-operation recovery state |
| CREATE | 4 | `src/vidbyte_cli/lib/runtime/clock.py` | Injectable wall/monotonic clock and sleeper |
| CREATE | 4 | `src/vidbyte_cli/lib/runtime/signals.py` | Local cancellation controller |
| CREATE | 5 | `src/vidbyte_cli/features/README.md` | Feature-slice ownership, file index, non-goals, and decision log |
| CREATE | 5 | `src/vidbyte_cli/features/__init__.py` | Feature-slice package boundary |
| CREATE | 5 | `src/vidbyte_cli/features/research/README.md` | Research boundary, file index, non-goals, and decision log |
| CREATE | 5 | `src/vidbyte_cli/features/research/__init__.py` | Research feature exports |
| CREATE | 5 | `src/vidbyte_cli/features/research/domain/README.md` | Research domain ownership, file index, non-goals, and decision log |
| CREATE | 5 | `src/vidbyte_cli/features/research/domain/__init__.py` | Research domain exports |
| CREATE | 5 | `src/vidbyte_cli/features/research/domain/enums.py` | Research wire/status/resource enums |
| CREATE | 5 | `src/vidbyte_cli/features/research/domain/models.py` | Runs, threads, sources, artifacts, pages, capabilities, exports |
| CREATE | 5 | `src/vidbyte_cli/features/research/domain/requests.py` | Strict mutation/list/export input models |
| CREATE | 5 | `src/vidbyte_cli/features/research/application/README.md` | Research use-case ownership, file index, non-goals, and decision log |
| CREATE | 5 | `src/vidbyte_cli/features/research/application/__init__.py` | Research application exports |
| CREATE | 5 | `src/vidbyte_cli/features/research/application/gateway.py` | HTTP-independent `ResearchGateway` protocol |
| CREATE | 5 | `src/vidbyte_cli/features/research/application/service.py` | Research use cases and operation lifecycle |
| CREATE | 5 | `src/vidbyte_cli/features/research/application/watcher.py` | Research adapter over generic polling |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/README.md` | Research command ownership, file index, non-goals, and decision log |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/__init__.py` | Research command exports |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/register.py` | First-class research group/subgroup registration |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/mutations.py` | Start/add/resume command classes |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/runs.py` | Status/watch/run-list command classes |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/resources.py` | Thread/source/artifact/capability command classes |
| CREATE | 6 | `src/vidbyte_cli/features/research/commands/exports.py` | Artifact/thread/portfolio export command classes |
| CREATE | 6 | `src/vidbyte_cli/features/research/presentation/README.md` | Research presentation ownership, file index, non-goals, and decision log |
| CREATE | 6 | `src/vidbyte_cli/features/research/presentation/__init__.py` | Research presentation exports |
| CREATE | 6 | `src/vidbyte_cli/features/research/presentation/presenter.py` | Human and structured research rendering |
| CREATE | 7 | `src/vidbyte_cli/features/research/infrastructure/README.md` | Research HTTP-adapter ownership, file index, non-goals, and decision log |
| CREATE | 7 | `src/vidbyte_cli/features/research/infrastructure/__init__.py` | Research infrastructure exports |
| CREATE | 7 | `src/vidbyte_cli/features/research/infrastructure/api_gateway.py` | Vidbyte API-backed research gateway |
| MODIFY | 1,2,3,4 | `pyproject.toml` | Dependencies, metadata, lint/type/build settings, console entry |
| MODIFY | 3,6,7 | `.env.example` | Config/auth variables and temporary research rollout gate |
| MODIFY | 1 | `.gitignore` | Python build/CI/local-state artifacts |
| MODIFY | 1,2,3,6,7 | `README.md` | Python setup, platform behavior, research commands, API integration |
| MODIFY | 1,2,3,4,5,6,7 | `docs/architecture.md` | Final dependency rules and feature-slice architecture |
| MODIFY | 1 | `docs/design/harness-runtime-and-cli-scaffold.md` | Mark earlier scaffold design as superseded for CLI evolution |
| MODIFY | 2 | `docs/design/python-cli-research-harness-program.md` | Record the isolated root-option preflight and typed failure classes discovered during implementation |
| MODIFY | 1,2,4,6,7 | `scripts/smoke.py` | Offline help/version/format/research/package smoke coverage |
| MODIFY | 1 | `src/vidbyte_cli/__init__.py` | Version export through metadata provider |
| MODIFY | 1 | `src/vidbyte_cli/__main__.py` | Thin return-code-to-SystemExit shim |
| MODIFY | 1,2,6,7 | `src/vidbyte_cli/cli.py` | Delegate bootstrap to `CliApplication` and register research |
| CREATE | 1 | `src/vidbyte_cli/commands/README.md` | Static command ownership, file index, non-goals, and decision log |
| MODIFY | 1,6,7 | `src/vidbyte_cli/commands/__init__.py` | Context-aware registration and research feature attachment |
| MODIFY | 3,4 | `src/vidbyte_cli/commands/auth/login.py` | Safe token input, verify-before-write, typed output |
| MODIFY | 3 | `src/vidbyte_cli/commands/auth/logout.py` | Idempotent multi-store clearing |
| MODIFY | 4 | `src/vidbyte_cli/commands/auth/whoami.py` | Auth gateway integration and structured output |
| MODIFY | 3 | `src/vidbyte_cli/commands/config/get.py` | Typed profile-aware config reads |
| MODIFY | 3 | `src/vidbyte_cli/commands/config/set.py` | Allow-listed atomic config writes |
| MODIFY | 4 | `src/vidbyte_cli/commands/harness/run.py` | Reusable idempotent submission and optional watching |
| MODIFY | 4 | `src/vidbyte_cli/commands/harness/status.py` | Typed API retrieval and output |
| MODIFY | 4 | `src/vidbyte_cli/commands/harness/list.py` | Typed list retrieval and output |
| MODIFY | 4 | `src/vidbyte_cli/commands/harness/catalog.py` | Manifest catalog retrieval/cache output |
| MODIFY | 3,4 | `src/vidbyte_cli/commands/setup/doctor.py` | Config provenance, keyring, API, and git diagnostics |
| MODIFY | 4 | `src/vidbyte_cli/lib/api/__init__.py` | Export transport collaborators |
| MODIFY | 4 | `src/vidbyte_cli/lib/api/client.py` | Real HTTPX client, timeouts, retry, decoding, redaction |
| MODIFY | 4 | `src/vidbyte_cli/lib/api/endpoints/auth.py` | Direct typed auth calls |
| MODIFY | 4 | `src/vidbyte_cli/lib/api/endpoints/harness.py` | Typed harness calls, cursors, idempotency |
| MODIFY | 3 | `src/vidbyte_cli/lib/auth/__init__.py` | Export credential collaborators |
| MODIFY | 3 | `src/vidbyte_cli/lib/auth/credentials.py` | Implement restricted fallback store and scoped records |
| MODIFY | 3 | `src/vidbyte_cli/lib/config/__init__.py` | Export config collaborators |
| MODIFY | 3 | `src/vidbyte_cli/lib/config/config.py` | Implement typed atomic config persistence |
| MODIFY | 3 | `src/vidbyte_cli/lib/config/paths.py` | Platformdirs locations and legacy compatibility |
| MODIFY | 2,4 | `src/vidbyte_cli/lib/errors/__init__.py` | Export typed errors/handler |
| MODIFY | 2,4 | `src/vidbyte_cli/lib/errors/cli_error.py` | Stable code, hint, retryability, request ID, safe cause |
| MODIFY | 4 | `src/vidbyte_cli/lib/git/repo_info.py` | Implement safe git inspection |
| MODIFY | 1,4 | `src/vidbyte_cli/lib/harness/base.py` | Keep Click typing strict; later add generic polling/idempotency/output integration |
| MODIFY | 4 | `src/vidbyte_cli/lib/harness/catalog.py` | Typed fetch/cache/version-skew behavior |
| MODIFY | 2,4 | `src/vidbyte_cli/lib/harness/context.py` | Share invocation services and later reuse transport/polling collaborators |
| MODIFY | 2,4 | `src/vidbyte_cli/lib/harness/errors.py` | Safe generic fallback and later typed transport/domain mapping |
| MODIFY | 2 | `src/vidbyte_cli/lib/harness/invocation.py` | Raise stable typed usage errors for missing inputs |
| MODIFY | 2 | `src/vidbyte_cli/lib/io/README.md` | Index prompt and terminal capability ownership |
| MODIFY | 2 | `src/vidbyte_cli/lib/io/__init__.py` | Export prompt and terminal contracts |
| MODIFY | 4 | `src/vidbyte_cli/lib/harness/types.py` | Explicit command mode semantics for read/submit/wait |
| MODIFY | 2 | `src/vidbyte_cli/lib/output/__init__.py` | Export output contracts |
| MODIFY | 2 | `src/vidbyte_cli/lib/output/logger.py` | Delegate to injected output manager/streams |
| MODIFY | 2,4 | `src/vidbyte_cli/lib/output/render.py` | Generic run/list/catalog presenters |
| MODIFY | 2 | `src/vidbyte_cli/lib/runtime/README.md` | Index root-option and output/error composition ownership |
| MODIFY | 2 | `src/vidbyte_cli/lib/runtime/application.py` | Parse root policy, inject Click streams, and delegate failures |
| MODIFY | 2 | `src/vidbyte_cli/lib/runtime/context.py` | Own invocation output, terminal, and error collaborators |
| MODIFY | 4 | `src/vidbyte_cli/types/api.py` | Stable transport/error/pagination compatibility models |
| MODIFY | 4 | `src/vidbyte_cli/types/harness.py` | Generic harness states/progress needed by watcher |
| MODIFY | 4 | `src/vidbyte_cli/types/manifest.py` | Strict manifest/version validation |
| MODIFY | 4 | `.claude/skills/add-harness/SKILL.md` | Document shared output/polling/idempotency integration rules |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | Runtime aligned with CLI and Vidbyte SDK | Wide version range requires CI matrix |
| Click | `>=8.1,<9` | Stable nested Python command framework | Decorator callbacks require disciplined adapters |
| Pydantic | `>=2.6,<3` | Strict config, wire, domain, and state validation | Major-version boundary must stay pinned |
| HTTPX | `>=0.27,<1` | Synchronous pooled HTTP transport | Retry policy must be implemented above basic transport |
| platformdirs | `>=4,<5` | Native config/cache/state paths | Migration must preserve legacy `~/.vidbyte` |
| keyring | `>=25,<26` | OS credential stores | Headless Linux may lack a viable backend |
| packaging | `>=24,<27` | CLI/manifest version comparison | Version semantics must remain PEP 440 |
| Ruff | Dev dependency | Lint and format gate | Rule expansion may expose baseline cleanup |
| mypy | Dev dependency, strict | Static type gate | Click dynamic callbacks need explicit annotations |
| build | Dev dependency | sdist/wheel creation | Packaging errors become required gate failures |
| twine | Dev dependency | Distribution metadata validation | No publication is authorized |
| Vidbyte API | `https://api.vidbyte.ai` plus localhost override | Auth, harness, research, export operations | Research read/export routes are assumed, not in PR #284 |
| OS keyring | macOS/Windows/Linux system service | Secure API-key storage | Service may be unavailable or locked |

No `tenacity`, `rich`, Typer, asyncio framework, DI container, or generated full API client
is added. Retry, output, and composition policies are small and domain-specific enough to
remain explicit.

---

## 11. Rollout & Deployment

- This is a breaking internal scaffold evolution, not a published-package migration. The
  current package is still marked as a scaffold.
- After explicit approval, fetch `origin` and create PR 1's worktree directly from the
  verified `origin/main`; do not switch or implement on the stale closed local branch.
- Use seven worktrees/branches:

| PR | Branch | Base |
|----|--------|------|
| 1 | `feat/python-cli-architecture-baseline` | `main` |
| 2 | `feat/cli-output-error-runtime` | PR 1 branch |
| 3 | `feat/cli-config-credential-platform` | PR 2 branch |
| 4 | `feat/cli-http-polling-idempotency` | PR 3 branch |
| 5 | `feat/research-domain-application` | PR 4 branch |
| 6 | `feat/research-command-surface` | PR 5 branch |
| 7 | `feat/research-api-integration` | PR 6 branch |

- The stack is opened as draft PRs so each review shows only its own delta. Merge in numeric
  order. If the repository uses squash merge, rebase/retarget every descendant onto the new
  `main` after each parent merge, then rerun the complete local and remote gates.
- The design document is committed first on PR 1 before any implementation commit.
- For each PR:
  1. Re-read the original request, approved design sections, and PR-specific manifest.
  2. Implement only that PR's scope.
  3. Perform the prosecution/defense self-review.
  4. Resolve every critical/notable refinement.
  5. Run `python -m pip install -e ".[dev]"`.
  6. Run `python scripts/run_ci.py`.
  7. Push, open/update the draft PR, and wait until required checks are green.
- PR 6 keeps research disabled by default with `VIDBYTE_EXPERIMENTAL_RESEARCH=1` available
  for smoke/manual review.
- PR 7 enables research by default after the API gateway is wired. A temporary kill switch
  may disable registration if the backend contract is unavailable during rollout.
- No backend deployment ordering is needed until PR 7. Before enabling PR 7, deploy the
  assumed read/capability/export routes and confirm their OpenAPI document.
- Rollback:
  - PRs 1-4 can be reverted in reverse order; legacy local files remain readable.
  - PRs 5-6 can be disabled or reverted without touching backend data.
  - PR 7 can disable research registration or revert the API adapter; admitted server runs
    continue independently.
  - Credential/config migration never deletes legacy files, preserving downgrade recovery.
- Package publication, PyPI trusted publishing, and claiming the `vidbyte` executable are
  follow-up release decisions and require separate authorization.

---

## 12. Open Questions

- [ ] Confirm that the seven PRs should be opened as a stacked draft chain as designed,
  rather than waiting for each PR to merge before creating the next.
- [ ] Confirm the final API-key read/export route paths in Sections 8.4-8.12. They are the
  canonical assumption for this design but are not present in PR #284.
- [ ] Confirm whether the backend will add stable `code`, `request_id`, and `retryable`
  fields to research error responses. The CLI can map by status without them but cannot
  provide equally precise automation semantics.
- [ ] Confirm whether `vidbyte-skills` will eventually relinquish the `vidbyte` executable.
  This design intentionally keeps `vidbyte-cli` to avoid a package-manager collision.
- [ ] Confirm whether `keyring` should be a required runtime dependency or an optional
  `secure-storage` extra. This design recommends required-with-safe-fallback because secure
  storage should be the default user experience.
- [ ] Confirm whether artifact `content` is returned inline or through a signed download
  URL. The CLI design supports either behind the gateway, but the wire model must choose one
  before PR 7.

---

## 13. Alternatives Considered

### Alternative 1: Rewrite the merged Python CLI again

- What: Discard the accepted PR #2/#3 Python scaffold and construct a new package from
  scratch around a different framework or directory tree.
- Why rejected: The canonical repository already has reviewed Click/Pydantic/HTTPX seams,
  an invocation layer, dynamic manifest support, and a class-first command convention.
  Replacing them would add migration risk without solving a user problem.

### Alternative 2: Move every `lib/` module into a new `core/` hierarchy

- What: Perform a mechanical package-wide rename before adding behavior.
- Why rejected: Folder naming alone does not create stronger boundaries, and the accepted
  architecture already gives `lib/` a clear shared-mechanism role. The design instead adds
  a `features/` boundary and forbids generic-to-feature imports, avoiding a large noisy PR.

### Alternative 3: Implement research as only `harness research`

- What: Use only the existing dynamic manifest namespace.
- Why rejected: Persistent threads, sources, artifacts, exports, pagination, and specialized
  watching are a product surface rather than a single generic run invocation. A first-class
  group is clearer while still sharing the runtime infrastructure.

### Alternative 4: Put all seven changes in one PR

- What: Build the platform, feature, and API integration in one branch.
- Why rejected: Reviewers could not distinguish mechanical/platform choices from research
  policy or API assumptions. The requested 6-8 PR program is satisfied with seven
  dependency-ordered deltas.

### Alternative 5: Create seven unrelated PRs all targeting main

- What: Base every branch directly on current main.
- Why rejected: Later PRs depend on types and infrastructure from earlier PRs, so their
  diffs would either duplicate code or fail CI. A stacked draft chain preserves narrow
  review deltas; descendants are rebased after parent merges.

### Alternative 6: Use async Click and `httpx.AsyncClient`

- What: Introduce an event loop for HTTP and polling.
- Why rejected: CLI requests and watches are sequential, and server concurrency lives in
  the backend. A synchronous pooled client has simpler cleanup, signal, typing, and Click
  integration with no user-visible throughput loss.

### Alternative 7: Use Typer instead of Click

- What: Replace Click with Typer for type-hint-driven declarations.
- Why rejected: Typer is built on Click and does not remove the need for application
  context, output, error, transport, or gateway architecture. The current reviewed command
  tree already uses Click directly.

### Alternative 8: Store API keys only in JSON

- What: Keep `~/.vidbyte/credentials.json` as the sole store.
- Why rejected: It is less secure for an end-user CLI. Keyring-first with an explicit
  restricted fallback provides stronger defaults while retaining headless compatibility.

### Alternative 9: Automatically reuse idempotency keys for identical prompts

- What: Hash a prompt and always reuse the same key.
- Why rejected: A user may intentionally run the same request twice. Keys are reused only
  within one logical operation or through explicit recovery.

### Alternative 10: Make mutation commands block by default

- What: Start a research run and keep the terminal attached until completion.
- Why rejected: Runs can be long and persistent. Admission should return durable IDs
  immediately; `--wait` and the separate `watch` command provide explicit blocking.

### Alternative 11: Expose full agent events in CLI watch

- What: Stream tool calls, queries, prompts, and internal execution events.
- Why rejected: The user explicitly reserved detailed real-time steps for the web product.
  The CLI exposes stable coarse progress suitable for humans and automation.

### Alternative 12: Add feature tests despite the selected no-tests workflow

- What: Add unit, HTTP, command, and binary test modules in these PRs.
- Why rejected: The user explicitly selected `design-doc-no-tests`. The design does not
  weaken existing verification: it adds a canonical lint/type/compile/smoke/package gate and
  cross-platform CI. Dedicated feature tests remain a recommended follow-up before a stable
  public release.
