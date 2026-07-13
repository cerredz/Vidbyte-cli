# Vidbyte CLI Architecture

The CLI is a thin, typed client for the Vidbyte platform. Harnesses execute entirely on the
Vidbyte backend; the CLI authenticates, submits harness runs, tracks status, and retrieves
results. It is written in Python (click + pydantic + httpx).

## The layers

```text
pyproject.toml [project.scripts]   console entry `vidbyte-cli` -> vidbyte_cli.cli:main
src/vidbyte_cli/cli.py             program bootstrap + central error trap (owns sys.exit)
                                   + two-pass argv peek that attaches a harness subtree
src/vidbyte_cli/commands/<group>/  one class per command: register() + execute()
src/vidbyte_cli/lib/api/client.py  ApiClient: base URL, API-key header, envelope unwrapping
src/vidbyte_cli/lib/api/endpoints/ typed endpoint groups (harness, auth, ...) on ApiClient
src/vidbyte_cli/lib/auth/          CredentialStore (~/.vidbyte/credentials.json)
src/vidbyte_cli/lib/config/        ConfigStore + VidbytePaths (single source of ~/.vidbyte)
src/vidbyte_cli/lib/git/           RepoInspector: origin URL, HEAD sha, branch, dirty state
src/vidbyte_cli/lib/output/        Logger + renderers (only modules that format output)
src/vidbyte_cli/lib/errors/        CliError with exit codes
src/vidbyte_cli/lib/harness/       the harness runtime (see below)
src/vidbyte_cli/harnesses/         hand-written harness modules (see below)
src/vidbyte_cli/types/             API + manifest models mirroring backend DTOs
```

## Rules

1. **Commands are thin.** A command class parses arguments, calls lib services, and hands
   results to a renderer. Commands never call httpx, touch the filesystem stores, or call
   `sys.exit` directly.
2. **All HTTP goes through `ApiClient`** via a typed endpoint group. New backend surfaces
   get a new file in `lib/api/endpoints/`, never inline requests.
3. **Errors are raised, not printed.** Anything user-facing raises `CliError(message,
   exit_code)`; the trap in `cli.py` renders it and exits. Unexpected errors exit 70.
4. **Secrets never log.** The API key may not appear in log lines, error messages, or
   rendered output.
5. **Paths have one source of truth.** Anything under `~/.vidbyte` resolves through
   `VidbytePaths`.
6. **Adding a static command group** = new folder under `commands/`, one class per command,
   registered in `commands/__init__.py`. Nothing else changes.

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
lib/harness/catalog.py        HarnessCatalog: fetch + cache manifests under ~/.vidbyte/manifests
lib/harness/factory.py        resolve a namespace to a HarnessModule (static wins, else
                              manifest) and attach it to the command tree
```

### Async registration

click builds its command tree synchronously, but a manifest arrives over the network. The
CLI does a **two-pass argv peek** in `cli.py`: pass 1 registers the static surface; pass 2,
only when argv is `harness <name> ...`, loads that one harness (cache-first) and attaches
its subtree before parsing. So `vidbyte-cli login` never touches the network, and only the
invoked harness loads. Manifests are cached under `~/.vidbyte/manifests` so `--help` works
offline.

### Integrating a harness in `src/vidbyte_cli/harnesses/<name>/`

Most harnesses need **no code here at all** — if the backend publishes a manifest, the
factory serves it via `ManifestHarness`. A hand-written module exists only to enrich UX
beyond what a manifest expresses. When you do write one, it is four steps (see
`harnesses/job_applier/` for a worked example):

1. `types.py` — the harness's own pydantic models (its "custom dataclasses").
2. `commands.py` — declare each command as a `HarnessCommandDef`; add a `to_invocation` /
   `present` hook only where the default doesn't fit.
3. `<name>.py` — a `BaseHarness` subclass binding `name` + `description` + `commands()`.
4. Register the instance in `harnesses/__init__.py` (`HARNESSES`).

Nothing in `commands/`, `cli.py`, or the click wiring changes — the factory discovers the
module by namespace. That invariant is what makes integration formulaic.

## Backend contract

The CLI targets the Vidbyte public API-key surface (`Authorization` via Vidbyte API key):

- `POST /harness/run` — submit an invocation (`{harness, command, args, options, repo}`)
- `GET /harness/get/{run_id}` — status, events, result
- `GET /harness/list` — the caller's runs
- `GET /harness/{name}/manifest` — a harness's command surface (drives dynamic commands)
- `GET /harness/catalog` — the available harnesses (distinct from the caller's runs)

Models in `types/api.py` and `types/manifest.py` mirror the backend DTOs; keep them in sync
with `backend/lib/dtos/harness.py` when the routes ship. The full system design lives in
[docs/design/harness-runtime-and-cli-scaffold.md](design/harness-runtime-and-cli-scaffold.md).
