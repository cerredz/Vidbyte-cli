# Vidbyte CLI Architecture

The CLI is a thin, typed client for the Vidbyte platform. Harnesses execute entirely on the
Vidbyte backend; the CLI authenticates, submits harness runs, tracks status, and retrieves
results. It is written in Python (click + pydantic + httpx).

## The layers

```text
pyproject.toml [project.scripts]   console entry `vidbyte-cli` -> vidbyte_cli.cli:main
src/vidbyte_cli/cli.py             thin reusable entry function returning an integer status
src/vidbyte_cli/__main__.py        outer `python -m` SystemExit boundary
src/vidbyte_cli/lib/runtime/       invocation composition, version, dispatch, error trap
                                   + two-pass argv inspection/one-harness attachment
src/vidbyte_cli/lib/io/            injected streams, terminal capabilities, prompt input
src/vidbyte_cli/commands/<group>/  one class per command: register() + execute()
src/vidbyte_cli/lib/api/client.py  ApiClient: base URL, API-key header, envelope unwrapping
src/vidbyte_cli/lib/api/endpoints/ typed endpoint groups (harness, auth, ...) on ApiClient
src/vidbyte_cli/lib/operations/   idempotency identity + prompt-free recovery journal
src/vidbyte_cli/lib/polling/      cancellation-aware generic remote-resource watching
src/vidbyte_cli/lib/auth/          scoped env/keyring/restricted-file credential boundary
src/vidbyte_cli/lib/config/        typed profiles, provenance, native paths, safe migration
src/vidbyte_cli/lib/git/           RepoInspector: origin URL, HEAD sha, branch, dirty state
src/vidbyte_cli/lib/output/        versioned documents + invocation output manager
src/vidbyte_cli/lib/errors/        stable codes, CliError metadata, central handler
src/vidbyte_cli/lib/harness/       the harness runtime (see below)
src/vidbyte_cli/harnesses/         hand-written harness modules (see below)
src/vidbyte_cli/features/          product-owned domain/application/adapters/presentation
src/vidbyte_cli/types/             API + manifest models mirroring backend DTOs
```

## Rules

1. **Commands are thin.** A command class parses arguments, calls lib services, and hands
   results to a renderer. Commands never call httpx, touch the filesystem stores, or call
   `sys.exit` directly.
2. **All HTTP goes through `ApiClient`** via a typed endpoint group. New backend surfaces
   get a new file in `lib/api/endpoints/`, never inline requests.
3. **Errors are raised, not printed.** Anything user-facing raises a classified `CliError`;
   `ErrorHandler` renders it and returns a status. Unexpected errors return 70 without
   exposing exception values. `--debug` adds redacted stack frames only.
4. **Secrets never log.** The API key may not appear in log lines, error messages, or
   rendered output.
5. **Paths have one source of truth.** Platform-native config/cache/state/data and legacy
   `~/.vidbyte` compatibility locations resolve through `VidbytePaths`.
6. **Adding a static command group** = new folder under `commands/`, one class per command,
   registered in `commands/__init__.py`. Nothing else changes.
7. **Reusable code does not terminate the process.** `CliApplication.run()` and `cli.main()`
   return an integer. Only generated console wrappers and `__main__.py` raise `SystemExit`.
8. **Process channels are injected.** Runtime and presentation code use `IOStreams`; direct
   writes to `sys.stdout`/`sys.stderr` stay at verification-script or outer process edges.
9. **One invocation owns one dependency graph.** `ApplicationContext` is constructed per
   run and creates optional harness services lazily, so help/version paths stay offline.
10. **Machine output is versioned.** Every JSON/JSONL record includes `schema_version` and
    `kind`. Human prose is not an automation contract.
11. **Stdout is results-only.** Progress, warnings, diagnostics, and all errors use stderr.
    JSON emits one final result; JSONL alone may stream state-transition result records.
12. **Prompt input is explicit.** A command accepts one positional value, UTF-8 file, or
   explicit `-` stdin marker, reads at most 20,001 characters, and never prompts merely
   because stdin is redirected.
13. **Secrets have separate precedence.** Credentials resolve environment → scoped OS
    keyring → warned restricted file. Environment credentials are never implicitly stored.
14. **Configuration is typed and attributable.** Command → environment → selected profile
    → default profile → built-in precedence is recorded per field.

15. **Retries preserve logical identity.** A mutation is retryable only with one stable
    idempotency key, serialized body, and request identity across attempts.
16. **Local cancellation is not remote cancellation.** Interrupted polling preserves the
    accepted operation record and prints a recovery command.
17. **Feature policy is transport-free.** Research domain and application packages import
    neither Click nor HTTPX; command and gateway adapters point inward.

## Output and failure contracts

Root presentation flags must precede the command:

```text
--format human|json|jsonl|none
--json
--profile NAME
--no-input
--color auto|always|never
--debug
```

`--json` is exactly an alias for `--format json`; pairing it with another format is a usage
error. `none` suppresses results and transitions but not actionable failures. Terminal
control is disabled when stderr is not a TTY, `TERM=dumb`, or `NO_COLOR` is present, even
when color was requested.

Base exit statuses are stable:

| Status | Meaning |
| --- | --- |
| `0` | success (including a normal downstream broken pipe) |
| `1` | operational failure |
| `2` | invalid command usage |
| `3` | partial research outcome when `--exit-status` is requested |
| `4` | authentication failure |
| `5` | credit exhaustion |
| `70` | internal software error |
| `130` | user interrupt |

Machine errors are version-1 `kind=error` documents on stderr with a stable code, exit
status, safe message, retryability, and optional hint/request ID. Private causes are never
serialized.

HTTP successes are bounded to 5 MB, require JSON content types, and validate as direct DTOs
or explicit envelopes. Error mapping uses status and stable metadata rather than backend
prose. Retryable statuses and transport failures receive at most three attempts with
bounded exponential backoff; POST requires an idempotency key.

## The harness runtime (dynamic commands)

Static command groups (rule 6) are hand-written classes. Harness *namespaces* are a
different mechanism: each harness exposes its own set of commands (`vidbyte-cli harness
<name> <command> ...`), and because harnesses live on the backend, those commands are
**described by a backend manifest and built at runtime** — so a new harness needs no CLI
release. `lib/harness/` is the mechanism; `harnesses/` is the policy.

```text
lib/harness/module.py         HarnessModule protocol — the whole contract (name, description,
                              commands(), register())
lib/harness/base.py           BaseHarness: register() builds the click subtree; dispatch()
                              runs the shared guard -> translate -> submit -> (await) ->
                              present -> map-errors lifecycle for every command
lib/harness/context.py        HarnessContext: injected services (endpoints, repo, creds,
                              logger, renderer) — the extensibility seam
lib/harness/types.py          HarnessCommandDef: a command as data + optional to_invocation /
                              present hooks with sensible defaults
lib/harness/manifest_harness.py  ManifestHarness(BaseHarness): satisfies the SAME contract
                              from a backend manifest, no per-command code
lib/harness/invocation.py     InvocationBuilder: the one layer that turns CLI params + a
                              command into a HarnessRunCreateRequest (parsing + agent-native
                              errors), shared by every command
lib/harness/catalog.py        HarnessCatalog: fetch + cache manifests in native user cache
lib/harness/registry.py       HarnessRegistry: owns both sources (static map + catalog) and
                              resolves a namespace to a HarnessModule (static wins, else
                              manifest), then attaches it to the command tree
```

### Async registration

click builds its command tree synchronously, but a manifest arrives over the network. The
CLI does a **two-pass argv inspection** in `lib/runtime/application.py`: pass 1 registers
the static surface; pass 2, only when argv is `harness <name> ...`, loads that one harness
(cache-first) and attaches its subtree before parsing. So `vidbyte-cli login` never touches
the network, and only the invoked harness loads. Manifests are cached under the
platform-native user cache directory so `--help` works offline; the historical
`~/.vidbyte/manifests` path remains readable and migratable.

## Verification boundary

`scripts/run_ci.py` is the one local and remote verification entry point. It runs Ruff,
strict mypy, byte compilation, offline CLI smoke, distribution build, Twine metadata checks,
and an installed-wheel smoke outside the source checkout. `.github/workflows/ci.yml` supplies
the OS/Python matrix and invokes that script without duplicating its steps.

The approved program intentionally adds no feature test files. This makes the smoke and
package gates startup/packaging evidence rather than proof of use-case correctness; the
constraint and residual risk are recorded in
`docs/design/python-cli-research-harness-program.md`.

## Research feature slice

The research product uses a vertical slice because its persistent thread/source/artifact
model is richer than the generic manifest-driven harness contract:

```text
features/research/domain          strict transport-free vocabulary and status policy
features/research/application     mutation, query, export, and watch use cases
features/research/commands        Click-only input adapters and static command registration
features/research/presentation    versioned documents, human views, coarse transitions
features/research/infrastructure  route constructors, wire DTOs, and production gateway
```

Domain and application imports remain independent of Click and HTTPX. Command registration
does no credential, filesystem, or network work. Large artifact reads require `--output`;
replacement additionally requires `--force`. Detailed agent-event telemetry remains
web-only, while the CLI watcher emits only status/source/artifact-count transitions.

The production gateway is lazy: static help registration does not resolve a credential or
construct an HTTP client. Confirmed mutation DTO vocabulary is translated at this boundary,
including `research_paper` to `paper` and `web_page` to `web`. Read, capability, and export
routes are isolated forward contracts until their backend implementation lands.

### Integrating a harness in `src/vidbyte_cli/harnesses/<name>/`

Most harnesses need **no code here at all** — if the backend publishes a manifest, the
`HarnessRegistry` serves it via `ManifestHarness`. A hand-written module exists only to
enrich UX beyond what a manifest expresses. When you do write one, it is four steps (see
`harnesses/software_engineering/` for the reference implementation, and the add-harness skill
under `.claude/skills/` for the full standard):

1. `types.py` — the harness's own pydantic models (its "custom dataclasses").
2. `commands.py` — declare each command as a `HarnessCommandDef`; add a `to_invocation` /
   `present` hook only where the default doesn't fit.
3. `harness.py` — a `BaseHarness` subclass binding `name` + `description` + `commands()`, and
   `requires_repo = True` when the harness runs against the caller's checkout.
4. Register the instance in `harnesses/__init__.py` (`HARNESSES`).

Nothing in `commands/`, `cli.py`, or the click wiring changes — the registry discovers the
module by namespace. That invariant is what makes integration formulaic.

## Backend contract

The CLI targets the Vidbyte public API-key surface (`Authorization` via Vidbyte API key):

- `POST /harness/run` — submit an invocation (`{harness, command, args, options, repo}`)
- `GET /harness/get/{run_id}` — status, events, result
- `GET /harness/list` — the caller's runs
- `GET /harness/{name}/manifest` — a harness's command surface (drives dynamic commands)
- `GET /harness/catalog` — the available harnesses (distinct from the caller's runs)

Research mutations confirmed from Vidbyte PR #284:

- `POST /research/run`
- `POST /research/threads/{thread_id}/run`
- `POST /research/runs/{run_id}/continue`

Forward read/export contracts assumed by the approved CLI design:

- `GET /research/runs/{run_id}` and `GET /research/runs`
- `GET /research/threads`
- `GET /research/threads/{thread_id}/sources`
- `GET /research/threads/{thread_id}/artifacts`
- `GET /research/artifacts/{artifact_id}`
- `GET /research/capabilities`
- `POST /research/exports` and `GET /research/exports/{export_id}`

All return direct DTOs; list routes return `{items, next_cursor}`. Missing capability/export
contracts map to an API-version error instead of falling back to browser-only behavior.

Models in `types/api.py` and `types/manifest.py` mirror the backend DTOs; keep them in sync
with `backend/lib/dtos/harness.py` when the routes ship. The full system design lives in
[docs/design/harness-runtime-and-cli-scaffold.md](design/harness-runtime-and-cli-scaffold.md).
