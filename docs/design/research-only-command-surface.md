# Design Doc: Research-Only Command Surface

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-15
**Last Updated:** 2026-08-15

---

## 1. Overview

`vidbyte-cli --help` currently advertises a nine-command harness product and a GitHub
account-linking flow that the Vidbyte backend does not implement. Every one of those commands
raises a typed `NOT_IMPLEMENTED` failure, and the routes they were written against
(`/harness/run`, `/harness/get/{run_id}`, `/harness/list`, `/harness/catalog`,
`/harness/{name}/manifest`) appear nowhere in `backend/lib/app/route_rules.py` on
`origin/main` — they were never built, not merely disabled behind a flag. This change deletes
that surface and everything that exists only to serve it, so a new user who types `--help`
sees only actions that succeed tonight against the live API: `login`, `logout`, `whoami`,
`doctor`, `config get|set`, and the seven `research` commands that map one-to-one onto the six
shipped `/api/v1/research/*` routes.

---

## 2. Goals & Non-Goals

### Goals

- Remove the `harness` command group (`run`, `status`, `list`, `catalog`) and the dynamic
  per-namespace subtree built from a backend manifest.
- Remove `connect github`.
- Remove every module that exists only to serve those commands: the harness runtime
  (`lib/harness/`), hand-written harness policy (`harnesses/`), repository inspection
  (`lib/git/`), the harness endpoint group, the harness/manifest wire types, the harness
  run renderer, and the harness logger.
- Remove the two-pass argv inspection machinery in `lib/runtime/application.py` whose entire
  purpose was attaching a harness namespace before Click dispatched.
- Remove the `CliError` subclasses that no longer have a raise site.
- Bring `README.md`, `docs/architecture.md`, `pyproject.toml`'s description, and every
  in-tree folder README into agreement with the surviving surface.
- Extend `scripts/smoke.py` with regression cases proving `harness` and `connect` are no
  longer commands, and add a verification script covering the whole testing plan.

### Non-Goals

- **No new commands.** `research deep-dive`, `research artifacts`, and a deep-dive result read
  require three backend routes that do not exist (the deep-dive route is
  `RouteAccess.SESSION`, and no API-key route publishes an `artifact_encrypted_id`). That work
  is a `vidbyte` PR and is out of scope here.
- **No changes to the seven research commands' behavior, options, output, or wire types.**
  They already match the shipped API exactly.
- **No removal of `CliErrorCode.NOT_IMPLEMENTED`** from `lib/errors/codes.py`. See §14.
- **No removal of `PromptInputResolver`** (`lib/io/prompt.py`) or the `ApiEnvelope` /
  `ApiError` / `ApiPagination` models in `types/api.py`. Both are already unreferenced on
  `main` *before* this change; removing them is unrelated cleanup and belongs in its own PR.
  Only the docstring in `types/api.py` that names a deleted file is corrected.
- **No deletion of historical design docs** under `docs/design/`. They record what was built
  and why; `docs/architecture.md` is the live document and is the one being corrected.
- **No feature test packs.** This repo's approved workflow verifies through
  `scripts/run_ci.py`; a dedicated verification script is added instead (§10).

---

## 3. Background & Context

### Why now

The CLI's research surface was rebuilt on `main` in PR #16 (`915e8a7`,
`feat: teach research to speak the shipped API`) and is now exact. `lib/api/endpoints/
research.py` states the constraint in its own docstring:

> These six are the entire surface an API key may call. There is no sources, artifacts,
> capabilities, exports, or run-listing route, so there is no method here for one.

That was verified against the backend route table. `backend/lib/app/route_rules.py:60-69` on
`origin/main` declares exactly six API-key research routes:

| Route | Scope | Billing |
| --- | --- | --- |
| `POST /api/v1/research/run` | `research:write` | `PRICED` 500 |
| `POST /api/v1/research/threads/{encrypted_id}/run` | `research:write` | `PRICED` 500 |
| `POST /api/v1/research/runs/{run_id}/continue` | `research:write` | `PRICED` 500 |
| `GET /api/v1/research/runs/{run_id}` | `research:read` | none |
| `GET /api/v1/research/portfolio` | `research:read` | none |
| `GET /api/v1/research/threads/{encrypted_id}` | `research:read` | none |

The harness group never got the same treatment. Grepping the same route table for `harness.`
or `"/harness` returns nothing. The commands are stubs that raise `NotImplementedFeature`, so
they cannot 404 — but they are still listed in `--help`, and a user who runs
`vidbyte-cli harness catalog` concludes the CLI is half-finished rather than that it is a
research CLI.

### Current state

`src/vidbyte_cli/commands/__init__.py` registers four groups plus four top-level commands.
The `harness` group is returned to `lib/runtime/application.py`, which performs a second argv
pass and attaches one harness namespace onto it:

```python
    def run(self, argv: Sequence[str] | None = None) -> int:
        arguments = list(sys.argv if argv is None else argv)
        try:
            program = self._build_program()
            harness_group = register_all_commands(program)
            inspection = self._preconfigure(arguments)
            if inspection is not None and inspection.attach_allowed:
                self._attach_harness(inspection, harness_group)
            return self._invoke(program, arguments)
```

`RootOptionInspector` (`lib/runtime/options.py`) exists to make that second pass safe — its
docstring says so directly: *"Click needs a harness namespace to exist before it dispatches…
So the root prefix is scanned once here."* It has a second, surviving job, covered in §6.3.

### Dependency island

The harness surface is self-contained. Nothing under `commands/research/`, `commands/auth/`
(except `connect_github.py`), `commands/config/`, or `commands/setup/` imports any of it. The
only edges into live code are:

- `lib/runtime/application.py` → `lib/harness/{catalog,registry}`
- `lib/runtime/context.py` → `lib/harness/context`
- `commands/__init__.py` → `commands/harness/*`, `commands/auth/connect_github`
- `lib/output/logger.py` ← imported **only** by `lib/harness/context.py`
- `lib/api/client.py::get_list` ← called **only** by `lib/api/endpoints/harness.py`
- `ResponseDecoder.many` ← called **only** by `ApiClient.get_list`

### Constraints from the field guide

Read per `field-guide/vidbyte-cli/init.md`:

- **`implementation-restraint.md`** — match existing comment density; a 3–6 line module
  docstring plus `#` comments on non-obvious invariants only, never templated
  `PURPOSE`/`FUNCTION INVENTORY` headers. Touch only the files this doc's §9 manifest names.
  A stateless single-use helper is a private method, not a new class. Verify with
  `python scripts/run_ci.py`, never ad-hoc commands. Line length is 100.
- **`typed-failures.md`** — every failure is a `CliError` subclass in `lib/errors/failures.py`
  carrying `description`/`trace`/`hint`; `handler.py` keeps exactly one `match`. No function
  may sit alone at the end of a module. This change *removes* three failure classes and
  corrects one `trace` string that names a deleted call path; it adds none.
- **Branch base** — `main` (`915e8a7`) is alive and is the correct base. The predecessor
  branch `feat/research-production-api-surface` is an ancestor of `main`, and the side branch
  `feat/research-api-wiring` (PR #17) is dead and must not be built on.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli --help` lists exactly these commands: `config`, `doctor`, `login`, `logout`,
   `research`, `whoami`. No `harness` group and no `connect` group.
2. `vidbyte-cli research --help` lists exactly: `add`, `resume`, `start`, `status`, `thread`,
   `threads`, `watch`.
3. `vidbyte-cli harness ...` exits 2 with `CliErrorCode.INVALID_ARGUMENT`, the same as any
   other unknown command.
4. `vidbyte-cli connect github` exits 2 with `CliErrorCode.INVALID_ARGUMENT`.
5. No command reachable from `--help` can raise `NotImplementedFeature`; the class has no
   raise site anywhere under `src/` and is deleted.
6. The seven research commands, four auth/setup commands, and two config commands keep their
   current arguments, options, exit statuses, human text, and machine documents byte for byte.
7. `--help` and `--version` still perform no filesystem or network access.
8. Invalid root syntax combined with a valid machine-output prefix (for example
   `--format json --not-an-option`) still emits a version-1 `kind=error` document on stderr —
   the behavior `RootOptionInspector` provides independently of harness attachment.
9. `--json` combined with a conflicting `--format` value still fails with
   `ConflictingOutputFormat`.
10. `import vidbyte_cli` still pulls in neither `click` nor `httpx`; `import vidbyte_cli.cli`
    still pulls in no `httpx`.
11. `ApplicationContext` exposes no harness factory, no `harness_context()`, and no
    `RuntimeError` guard keyed on harness construction.
12. `AuthenticationRequired.trace` names only call paths that exist after this change.

### Non-Functional Requirements

- **Startup cost:** strictly lower. `register_all_commands` imports six fewer command modules
  and the harness runtime is never imported. `--help` must not regress.
- **Security:** unchanged. No credential, path, or transport behavior is touched. The
  `x-api-key` header, redirect refusal, relative-path guard, and response bounds are
  untouched.
- **Observability:** unchanged. The machine error envelope (`schema_version`, `kind`, `code`,
  `exit_code`, `description`, `trace`, `file_path`) keeps its shape.
- **Reliability:** no runtime behavior change for surviving commands; this is a deletion.
- **Reversibility:** every deleted file is recoverable from git history at `915e8a7`. The
  harness runtime can be restored wholesale if and when `/harness/*` ships.

---

## 5. High-Level Design

This is a deletion, not a rewrite. Three things happen, in dependency order.

**First, the command registrations go.** `commands/__init__.py` stops building the `harness`
and `connect` groups and stops returning anything, because the only reason it returned the
`harness` group was so `CliApplication` could attach a subtree to it. That single edit makes
30 files unreachable.

**Second, the runtime machinery that existed to serve those registrations goes.**
`CliApplication.run` collapses from build → register → inspect → attach → dispatch to
build → register → configure → dispatch. `_attach_harness`, `_harness_namespace`, and the
`_GENERIC_HARNESS_VERBS` constant are deleted outright. `RootOptionInspector` **stays**: its
harness-namespace job disappears, but its second job — settling `--format` and `--debug`
before Click can raise a syntax error through `ErrorHandler` — is what makes requirement 8
hold, and nothing else provides it. Its `RootInspection` result sheds the two fields that only
attachment read (`command_arguments`, `attach_allowed`). `ApplicationContext` sheds the
harness factory, the lazily-built harness context, and the `configure()` guard that existed
solely because a constructed `HarnessContext` had captured an `OutputManager`.

**Third, the orphans go.** Deleting the endpoint group orphans `ApiClient.get_list`, which
orphans `ResponseDecoder.many`. Deleting `lib/harness/context.py` orphans
`lib/output/logger.py`. Deleting the four command stubs and `connect_github.py` orphans
`NotImplementedFeature`; deleting `lib/harness/errors.py` and `lib/harness/invocation.py`
orphans `HarnessInvocationFailed` and `MissingHarnessArgument`. Leaving any of these behind
would make the removal incomplete rather than minimal, so each is deleted in the same change.

```
BEFORE                                    AFTER
------                                    -----
cli.main                                  cli.main
  CliApplication.run                        CliApplication.run
    _build_program                            _build_program
    register_all_commands ──► harness grp     register_all_commands  (returns None)
    _preconfigure ──► RootInspection          _preconfigure          (returns None)
    _attach_harness                           _invoke ──► Click
      _harness_namespace
      HarnessRegistry.attach
        static_harness_map  (harnesses/)
        HarnessCatalog      (network)
    _invoke ──► Click

commands: login logout whoami doctor      commands: login logout whoami doctor
          connect github                            config get|set
          harness run|status|list|catalog           research start|add|resume|
          harness <namespace> <cmd>  (dyn)                   status|watch|threads|thread
          config get|set
          research start|add|resume|
                   status|watch|threads|thread
```

---

## 6. Detailed Design

### 6.1 Static command registration

**File(s):** `src/vidbyte_cli/commands/__init__.py`
**Type:** Modified

#### What it does

The single registration point for the CLI's static command surface. After this change there
is no dynamic surface at all, so it registers everything and returns nothing.

#### Interface / API

```python
def register_all_commands(program: click.Group) -> None:
    # Attaches every command group to the root program; the surface is entirely static.
```

#### Logic / Algorithm

1. Drop the imports of `ConnectGithubCommand` and the four `commands.harness.*` classes.
2. Drop the `connect` and `harness` group construction blocks.
3. Keep the `research` and `config` groups and the four top-level commands, in their current
   order.
4. Change the return type from `click.Group` to `None` and remove the `return harness` line.
5. Rewrite the module docstring: it currently describes the static/dynamic seam, which no
   longer exists.

#### Edge Cases & Error Handling

- Click raises `NoSuchCommand` for `harness`/`connect` exactly as for any other unknown token;
  `ErrorHandler` already maps `click.UsageError` to `InvalidCommandUsage` (exit 2,
  `INVALID_ARGUMENT`). No new handling is needed — that is the point.

---

### 6.2 Application composition root

**File(s):** `src/vidbyte_cli/lib/runtime/application.py`
**Type:** Modified

#### What it does

Runs one invocation: build the Click tree, settle root policy, dispatch inside a single error
trap, return a status.

#### Interface / API

```python
class CliApplication:
    def run(self, argv: Sequence[str] | None = None) -> int:
    def _build_program(self) -> click.Group:
    def _preconfigure(self, argv: Sequence[str]) -> None:
    def _invoke(self, program: click.Group, argv: Sequence[str]) -> int:
    def _configure_context(self, values: RootOptionValues) -> None:
    def _resolve_output_format(self, value: str | None, as_json: bool) -> OutputFormat | None:
```

#### Logic / Algorithm

1. Delete the `_GENERIC_HARNESS_VERBS` module constant.
2. Delete the `register_all_commands` return binding, `_attach_harness`, and
   `_harness_namespace`.
3. Delete the `from ...harnesses import static_harness_map`, `from ..harness.catalog import
   HarnessCatalog`, and `from ..harness.registry import HarnessRegistry` imports, and the
   `RootInspection` import (no longer referenced by a signature).
4. `run()` becomes: build program → `register_all_commands(program)` → `self._preconfigure
   (arguments)` → `return self._invoke(program, arguments)`, all inside the existing
   `try/except/finally` trap.
5. `_preconfigure` returns `None`. It still calls `RootOptionInspector(argv).inspect()`,
   still returns early when the scan is `None` (invalid choice value), and still skips
   `_configure_context` when `exits_before_command` is set, so `--help` never reads a file.
6. Change the root group's help string from
   `"Universal Vidbyte CLI: auth, harness runs, config"` to
   `"Vidbyte CLI: authenticate and run Vidbyte research threads."`
7. Rewrite the module docstring: the two-pass explanation is deleted; what remains is the
   composition-root and error-boundary description plus why root flags are overrides.

#### Edge Cases & Error Handling

- `_preconfigure` returning `None` for invalid root syntax must still leave output policy
  configured, or requirement 8 breaks. `RootOptionInspector._invalid()` returns a
  `RootInspection` (not `None`) with `exits_before_command` false, so `_configure_context` runs
  and Click's error renders as JSON. Only a genuinely unparseable *choice value* returns
  `None`, and that path intentionally stays service-free.
- `--help`/`--version` short-circuit before `_configure_context`, so no config file is read.

---

### 6.3 Root option inspection

**File(s):** `src/vidbyte_cli/lib/runtime/options.py`
**Type:** Modified

#### What it does

Scans the root-option prefix of argv once, cheaply, so `--format` and `--debug` take effect
before Click can raise a syntax error through `ErrorHandler`. This is the surviving reason the
inspector exists; the harness-namespace reason is gone.

#### Interface / API

```python
@dataclass(frozen=True)
class RootInspection:
    """Validated root policy, and whether the invocation exits before any command runs."""

    values: RootOptionValues
    exits_before_command: bool = False
```

#### Logic / Algorithm

1. Delete the `command_arguments` and `attach_allowed` fields from `RootInspection`.
2. `inspect()` no longer builds `suffix`; it returns
   `RootInspection(self._freeze(), exits_before_command)`.
3. `_invalid()` returns `RootInspection(self._freeze())`.
4. Delete the `Sequence` import if it becomes unused — it does not; `__init__` still takes
   `Sequence[str]`.
5. Rewrite the module docstring: replace the harness framing with the output-policy framing,
   keeping the "an unpassed option stays `None`" paragraph, which is still load-bearing for
   configuration precedence.

#### Edge Cases & Error Handling

- The scanner still stops at the first positional token and still refuses `--flag=value` for
  boolean flags, matching Click. Neither behavior was harness-specific.
- `self._index` advancement past `--` is retained; the suffix is simply not returned.

---

### 6.4 Invocation dependency graph

**File(s):** `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

#### What it does

Builds and owns one invocation's services. After this change it owns no optional harness
graph, so every service it builds is reachable from a live command.

#### Interface / API

```python
class ApplicationContext:
    def __init__(
        self,
        streams: IOStreams,
        *,
        environment: Mapping[str, str] | None = None,
        paths: VidbytePaths | None = None,
        verifier_factory: Callable[[], CredentialVerifier] | None = None,
    ) -> None:
    def configure(self, options: InvocationOptions, config: ResolvedConfig) -> None:
```

#### Logic / Algorithm

1. Delete the `harness_factory` positional parameter, `self._harness_factory`,
   `self._harness_context`, `harness_context()`, and `_build_harness_context()`.
2. Delete the `from ..harness.context import HarnessContext` import and the now-unused
   `Callable` usage stays (still needed by `verifier_factory`).
3. Delete the first branch of `configure()`:
   ```python
   if self._harness_context is not None and options != self.options:
       raise RuntimeError("Invocation options cannot change after harness construction.")
   ```
   Its only justification was that a constructed `HarnessContext` had captured an
   `OutputManager`. The idempotence short-circuit on the next two lines stays.
4. Rewrite the module docstring paragraph that explains why root options arrive before "an
   optional harness context can capture the wrong OutputManager".

#### Edge Cases & Error Handling

- `scripts/test_login_key_verification.py` constructs `ApplicationContext(streams,
  environment=…, paths=…, verifier_factory=…)` — every argument after `streams` is already
  keyword, so making them keyword-only is source-compatible with the existing suite.
- Removing the `RuntimeError` guard cannot regress anything: with no harness context there is
  no second `OutputManager` holder, and `configure()` rebuilds the manager on every real
  change exactly as before.

---

### 6.5 Typed failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Holds one `CliError` subclass per failure the CLI can raise, with the agent-native prose.

#### Logic / Algorithm

1. Delete `NotImplementedFeature` — after §6.1 and §6.9 it has zero raise sites.
2. Delete `HarnessInvocationFailed` — raised only by `lib/harness/errors.py`.
3. Delete `MissingHarnessArgument` — raised only by `lib/harness/invocation.py`.
4. Rewrite `AuthenticationRequired.trace`, which currently names two deleted symbols:

   ```text
   #  before
   trace=(
       "A command requiring the Vidbyte API — BaseHarness.dispatch through "
       "HarnessContext.require_credentials, or WhoamiCommand.execute directly — "
       "reached CredentialResolver.resolve, which found no key in the environment, "
       "the keyring, or the restricted file for this profile and host."
   ),
   #  after
   trace=(
       "A command requiring the Vidbyte API — a research command through "
       "ApplicationContext.api_client, or WhoamiCommand.execute directly — reached "
       "CredentialResolver.resolve, which found no key in the environment, the "
       "keyring, or the restricted file for this profile and host."
   ),
   ```

5. Leave every other class untouched. `ResearchThreadIdInvalid`, `ApiPermissionDenied`,
   `ApiRequestConflicted`, and the rest already describe research paths correctly.

#### Edge Cases & Error Handling

- `CliErrorCode.NOT_IMPLEMENTED` stays in `codes.py`. `codes.py` declares "Every value here is
  a public contract"; removing a shipped code string from a machine-readable enum is a
  breaking change for any agent matching on it, and it costs one line to keep. See §14.
- No `handler.py` change: none of the three deleted classes appears in its `match`.

---

### 6.6 Transport

**File(s):** `src/vidbyte_cli/lib/api/client.py`, `src/vidbyte_cli/lib/api/response.py`
**Type:** Modified

#### What it does

`ApiClient` is the CLI's only HTTP speaker; `ResponseDecoder` is its only success-body reader.

#### Logic / Algorithm

1. `client.py`: delete `get_list`. Its two callers were `HarnessEndpoints.list_runs` and
   `HarnessEndpoints.list_catalog`.
2. `response.py`: delete `ResponseDecoder.many`, whose only caller was `get_list`. Remove the
   now-unused `TypeAdapter` import.
3. `response.py`: amend the `ResponseShape` docstring, which currently justifies having two
   members by referring to `many`:

   ```python
   class ResponseShape(StrEnum):
       """How a route wraps the payload a caller actually wants.

       The research surface returns its DTO directly; the older public resources wrap it in
       `{success, data}`. Every route declares which, so adding one cannot silently unwrap
       something that was never wrapped.
       """
   ```

4. Keep `ResponseShape.ENVELOPE`, `ResponseDecoder._unwrap`, and the `ENVELOPE` defaults on
   `get`/`post`. They are the declared default for any future non-research route and are not
   orphaned by this change.

#### Edge Cases & Error Handling

- No behavior change for research: every research call already passes
  `shape=ResponseShape.DIRECT` explicitly, and `post_direct` (used by auth) does not route
  through the deleted code.

---

### 6.7 Presentation

**File(s):** `src/vidbyte_cli/lib/output/render.py`, `src/vidbyte_cli/lib/output/logger.py`
**Type:** Deleted

#### What it does (today)

`render.py` holds `RunRenderer`, whose three methods all raise `NotImplementedFeature` and
whose only consumer was the harness lifecycle. `logger.py` holds `Logger`, imported only by
`lib/harness/context.py`.

#### Logic / Algorithm

1. Delete both files. Neither is exported from `lib/output/__init__.py`, so the package facade
   needs no edit.
2. Research presentation lives in `commands/research/render.py` (`ResearchRenderer`) and is
   untouched. Progress and warnings go through `OutputManager`, also untouched.

---

### 6.8 Wire types

**File(s):** `src/vidbyte_cli/types/harness.py`, `src/vidbyte_cli/types/manifest.py`
**Type:** Deleted; `src/vidbyte_cli/types/api.py` Modified

#### Logic / Algorithm

1. Delete `types/harness.py` (`HarnessRun`, `HarnessRunCreateRequest`, `HarnessSummary`,
   `HarnessRepoRef`) and `types/manifest.py` (`HarnessManifest`, `ArgSpec`, `OptionSpec`).
2. `types/api.py`: correct the module docstring, which currently reads *"Harness run models
   live in types/harness.py (split per the types/api.ts:38 review comment)…"* and would name a
   deleted file. Replace with a sentence describing the envelope and `KeyIdentity` only.
3. Leave `KeyIdentity` (used by auth), and leave `ApiEnvelope`/`ApiError`/`ApiPagination`
   (already unreferenced before this change — see §2 Non-Goals).

---

### 6.9 Deleted command and runtime packages

**File(s):** `src/vidbyte_cli/commands/harness/`, `src/vidbyte_cli/commands/auth/
connect_github.py`, `src/vidbyte_cli/harnesses/`, `src/vidbyte_cli/lib/harness/`,
`src/vidbyte_cli/lib/git/`, `src/vidbyte_cli/lib/api/endpoints/harness.py`
**Type:** Deleted

#### Logic / Algorithm

Delete each directory or file whole. Enumerated individually in §9. `commands/auth/__init__.py`
is empty and stays; `lib/api/endpoints/__init__.py` is empty and stays.

#### Edge Cases & Error Handling

- `lib/git/` becomes an empty package and is removed entirely (`__init__.py` is empty,
  `repo_info.py` holds `RepoInspector`, whose only consumer was `HarnessContext`).
- `harnesses/__init__.py` ends in a module-level `static_harness_map()` function — it goes
  with the package, so the field guide's "no function alone" rule needs no separate fix.

---

### 6.10 Agent skill

**File(s):** `.claude/skills/add-harness/SKILL.md`
**Type:** Deleted

#### What it does

Instructs an agent to build a hand-written harness against `lib/harness/` and `harnesses/`.
Both are deleted, so the skill would direct an agent to write code against modules that do not
exist. Delete it rather than leave a live instruction pointing at nothing.

---

### 6.11 Documentation

**File(s):** `README.md`, `docs/architecture.md`, `pyproject.toml`,
`src/vidbyte_cli/README.md`, `src/vidbyte_cli/commands/README.md`,
`src/vidbyte_cli/lib/README.md`, `src/vidbyte_cli/lib/api/README.md`,
`src/vidbyte_cli/lib/output/README.md`, `src/vidbyte_cli/lib/runtime/README.md`
**Type:** Modified

#### Logic / Algorithm

1. **`README.md`** — rewrite the opening paragraph and status note to describe a research
   client; delete the six `harness`/`connect` rows from the command table; change the global-
   options example from `harness list` to `research threads`; replace the "Architecture"
   section's harness-sub-CLI paragraph; drop the follow-up bullet about implementing
   `harness run/status/list`; keep the other follow-ups and add one for the deep-dive backend
   gap.
2. **`docs/architecture.md`** — remove `lib/git/`, `lib/harness/`, `harnesses/` from the layer
   map and the "two-pass argv inspection" line; amend rule 6 (registration no longer returns a
   group), rule 9 (no optional harness services); delete the entire "The harness runtime
   (dynamic commands)", "Async registration", and "Integrating a harness" sections; replace
   the "Backend contract" section's five `/harness/*` routes with the six shipped
   `/api/v1/research/*` routes and their scopes.
3. **`pyproject.toml`** — `description` becomes
   `"Vidbyte CLI: authentication, research threads, and configuration"`. This is published
   package metadata and is validated by the existing `twine check` gate.
4. **Folder READMEs** — remove the harness/manifest/`render.py`/`logger.py` lines from the
   Files and Non-goals sections, and append a dated Log entry to each, matching the existing
   `## Log` convention.

---

## 7. Data Model Changes

N/A — this repository has no database, no persisted schema change, and no migration. The
on-disk config and credential documents (`ConfigDocument`, `CredentialDocument`, both
`schema_version: 1`) are untouched, and the manifest cache directory the harness catalog used
is simply no longer written or read. A stale `~/.vidbyte/manifests` or native-cache manifest
directory left by an earlier install is inert: nothing reads it, and this change does not
delete it.

---

## 8. API Changes

N/A — the CLI is a client. No Vidbyte API endpoint is added, modified, or deprecated. The set
of routes this CLI calls shrinks from eleven to seven:

**Still called (7):**

| Method | Path | Command |
| --- | --- | --- |
| POST | `/api/skills/auth/validate` | `login`, `whoami` |
| POST | `/api/v1/research/run` | `research start` |
| POST | `/api/v1/research/threads/{encrypted_id}/run` | `research add` |
| POST | `/api/v1/research/runs/{run_id}/continue` | `research resume` |
| GET | `/api/v1/research/runs/{run_id}` | `research status`, `research watch` |
| GET | `/api/v1/research/portfolio` | `research threads` |
| GET | `/api/v1/research/threads/{encrypted_id}` | `research thread` |

**No longer called (5, none of which the backend serves):** `POST /harness/run`,
`GET /harness/get/{run_id}`, `GET /harness/list`, `GET /harness/catalog`,
`GET /harness/{name}/manifest`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
| --- | --- | --- |
| CREATE | `docs/design/research-only-command-surface.md` | This design doc |
| CREATE | `scripts/test_research_only_surface.py` | Phase 5 verification script |
| DELETE | `src/vidbyte_cli/commands/harness/__init__.py` | Harness group removed |
| DELETE | `src/vidbyte_cli/commands/harness/run.py` | No `/harness/run` route exists |
| DELETE | `src/vidbyte_cli/commands/harness/status.py` | No `/harness/get` route exists |
| DELETE | `src/vidbyte_cli/commands/harness/list.py` | No `/harness/list` route exists |
| DELETE | `src/vidbyte_cli/commands/harness/catalog.py` | No `/harness/catalog` route exists |
| DELETE | `src/vidbyte_cli/commands/auth/connect_github.py` | No linkage flow exists |
| DELETE | `src/vidbyte_cli/harnesses/__init__.py` | Static harness registry unreachable |
| DELETE | `src/vidbyte_cli/harnesses/software_engineering/__init__.py` | Harness policy removed |
| DELETE | `src/vidbyte_cli/harnesses/software_engineering/commands.py` | Harness policy removed |
| DELETE | `src/vidbyte_cli/harnesses/software_engineering/harness.py` | Harness policy removed |
| DELETE | `src/vidbyte_cli/harnesses/software_engineering/render.py` | Harness policy removed |
| DELETE | `src/vidbyte_cli/harnesses/software_engineering/types.py` | Harness policy removed |
| DELETE | `src/vidbyte_cli/lib/harness/__init__.py` | Harness runtime removed |
| DELETE | `src/vidbyte_cli/lib/harness/README.md` | Package removed |
| DELETE | `src/vidbyte_cli/lib/harness/base.py` | Harness runtime removed |
| DELETE | `src/vidbyte_cli/lib/harness/catalog.py` | Manifest fetch/cache removed |
| DELETE | `src/vidbyte_cli/lib/harness/context.py` | Harness DI graph removed |
| DELETE | `src/vidbyte_cli/lib/harness/errors.py` | Harness error mapping removed |
| DELETE | `src/vidbyte_cli/lib/harness/invocation.py` | Invocation builder removed |
| DELETE | `src/vidbyte_cli/lib/harness/manifest_harness.py` | Manifest adapter removed |
| DELETE | `src/vidbyte_cli/lib/harness/module.py` | Harness protocol removed |
| DELETE | `src/vidbyte_cli/lib/harness/registry.py` | Namespace resolution removed |
| DELETE | `src/vidbyte_cli/lib/harness/types.py` | `HarnessCommandDef` removed |
| DELETE | `src/vidbyte_cli/lib/git/__init__.py` | Only consumer was `HarnessContext` |
| DELETE | `src/vidbyte_cli/lib/git/repo_info.py` | Only consumer was `HarnessContext` |
| DELETE | `src/vidbyte_cli/lib/api/endpoints/harness.py` | Targets routes that do not exist |
| DELETE | `src/vidbyte_cli/lib/output/render.py` | `RunRenderer` had no live consumer |
| DELETE | `src/vidbyte_cli/lib/output/logger.py` | Imported only by `lib/harness/context.py` |
| DELETE | `src/vidbyte_cli/types/harness.py` | Harness wire models removed |
| DELETE | `src/vidbyte_cli/types/manifest.py` | Manifest wire models removed |
| DELETE | `.claude/skills/add-harness/SKILL.md` | Instructs against deleted modules |
| MODIFY | `src/vidbyte_cli/commands/__init__.py` | Drop harness/connect; return `None` |
| MODIFY | `src/vidbyte_cli/lib/runtime/application.py` | Drop attachment pass; fix help text |
| MODIFY | `src/vidbyte_cli/lib/runtime/options.py` | Drop attachment-only fields |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Drop harness factory and guard |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Delete 3 classes; fix one `trace` |
| MODIFY | `src/vidbyte_cli/lib/api/client.py` | Delete orphaned `get_list` |
| MODIFY | `src/vidbyte_cli/lib/api/response.py` | Delete orphaned `many`; fix docstring |
| MODIFY | `src/vidbyte_cli/types/api.py` | Docstring names a deleted file |
| MODIFY | `src/vidbyte_cli/README.md` | Drop harness-policy references |
| MODIFY | `src/vidbyte_cli/commands/README.md` | No static/dynamic seam remains |
| MODIFY | `src/vidbyte_cli/lib/README.md` | Drop harness-mechanics references |
| MODIFY | `src/vidbyte_cli/lib/api/README.md` | Stale `get_list`/`/harness/*` paragraph |
| MODIFY | `src/vidbyte_cli/lib/output/README.md` | Drop `render.py`/`logger.py` rows |
| MODIFY | `src/vidbyte_cli/lib/runtime/README.md` | Drop attachment references |
| MODIFY | `docs/architecture.md` | Layer map, rules 6/9, harness sections, backend contract |
| MODIFY | `README.md` | Command table, intro, architecture, follow-ups |
| MODIFY | `pyproject.toml` | Package description |
| MODIFY | `scripts/smoke.py` | Replace harness cases with absence assertions |
| MODIFY | `scripts/run_ci.py` | Register the new verification script as a gate |
| MODIFY | `scripts/README.md` | Document the new script; Log entry |

**Totals: 2 created, 31 deleted, 20 modified.**

---

## 10. Testing Plan

Verification runs through `scripts/test_research_only_surface.py`, executed directly and
wired into `scripts/run_ci.py` alongside the existing gates. Cases that assert on the *public
process contract* (help output, exit statuses, error codes) run the CLI through
`python -m vidbyte_cli` in a subprocess with an isolated state root, matching `smoke.py`'s
approach; cases that assert on *module structure* import the package directly.

### Unit Tests

`describe('command surface')`

- `it('exposes exactly six top-level commands')` — [Silent Failure] the dangerous outcome is a
  group surviving registration and going unnoticed because `--help` still exits 0. Asserts the
  exact set `{config, doctor, login, logout, research, whoami}`, not merely the absence of
  `harness`.
- `it('exposes exactly seven research subcommands')` — [Silent Failure] guards the inverse
  regression: over-deleting and silently dropping a working research command.
- `it('rejects `harness` as an unknown command with exit 2 / INVALID_ARGUMENT')` —
  [Hidden Assumption] the removal assumed Click's unknown-command path, not a special case.
- `it('rejects `harness software-engineering fix` with exit 2')` — [Edge Case] the deepest
  previously-valid path; a partially-removed registration could still resolve the namespace.
- `it('rejects `connect github` with exit 2 / INVALID_ARGUMENT')` — [Hidden Assumption]
- `it('never emits a NOT_IMPLEMENTED error code from any reachable command')` — [Silent
  Failure] walks every command and subcommand in the built tree and asserts none of their
  callbacks can reach a deleted stub.

`describe('module structure')`

- `it('has no importable vidbyte_cli.lib.harness')` — [Hidden Failure] a leftover
  `__pycache__` or a stray re-export would keep the module importable while the source is
  gone.
- `it('has no importable vidbyte_cli.harnesses, lib.git, types.harness, types.manifest,
  lib.output.render, lib.output.logger, lib.api.endpoints.harness, commands.harness,
  commands.auth.connect_github')` — [Hidden Failure] same, one case per module.
- `it('defines no NotImplementedFeature, HarnessInvocationFailed, or MissingHarnessArgument')`
  — [Silent Failure] a class kept "just in case" is dead code that reads as live.
- `it('keeps CliErrorCode.NOT_IMPLEMENTED in the published enum')` — [Hidden Assumption] the
  deliberate asymmetry in §14; a future cleanup that removes it should fail here first.
- `it('exposes no harness_context attribute on ApplicationContext')` — [Hidden Failure]
- `it('RootInspection carries no command_arguments or attach_allowed field')` — [Hidden
  Failure]
- `it('ApiClient exposes no get_list and ResponseDecoder exposes no many')` — [Hidden Failure]
- `it('no source file under src/ mentions harness, HarnessRun, or RepoInspector')` —
  [Silent Failure] the whole-tree sweep that catches a missed docstring or import; the most
  likely real defect in a deletion of this size.

`describe('surviving behavior')`

- `it('keeps AuthenticationRequired trace free of deleted symbols')` — [Silent Failure] a
  stale `trace` is authored prose no type checker or linter will ever flag, and it is the
  field agents read to repair their own invocation.
- `it('still fails --json with a conflicting --format value')` — [Hidden Assumption] the
  conflict is resolved inside `_resolve_output_format`, on the path being edited.
- `it('still emits a machine error document for invalid root syntax after --format json')` —
  [Hidden Failure] this is requirement 8 and the single most plausible regression: deleting
  `attach_allowed` could tempt a simplification of `_invalid()` that returns `None`, which
  would silently downgrade the JSON error to human text on stderr.
- `it('still emits a machine error for an unknown command after --format json')` — [Hidden
  Failure]
- `it('returns exit 0 and reads no file for --help and --version')` — [Hidden Assumption]
  `exits_before_command` must still short-circuit `_configure_context`; asserted by pointing
  every state root at a nonexistent directory and requiring exit 0.
- `it('keeps doctor working end to end against an empty isolated home')` — [Edge Case] the
  one command that exercises config resolution and credential lookup with zero state.
- `it('keeps research thread ID validation local — a bad token exits 2, not 4')` — [Silent
  Failure] if credential resolution moved ahead of argument validation, this would exit 4
  (`AUTH_REQUIRED`) and look like a login problem rather than a typo.

`describe('import boundaries')`

- `it('imports vidbyte_cli without click or httpx')` — [Hidden Failure] already covered by
  `smoke.py`; re-asserted because this change edits the import graph of every module on that
  path.
- `it('imports vidbyte_cli.cli without httpx')` — [Hidden Failure]

### Integration Tests

Covered by the same script, since the CLI's integration surface *is* its process contract.

- **Flow: a full `--help` walk.** Build the Click tree in-process and recursively render help
  for every command and subcommand, asserting every invocation exits 0. This is the flow that
  catches a registration referencing a deleted import, which would otherwise only surface as
  an `ImportError` on the specific command a user happened to run.
- **Mocked vs. real:** nothing is mocked and nothing is networked. The isolated state root and
  the null keyring backend are the only substitutions, matching `smoke.py`. No live Vidbyte
  endpoint is contacted, so the script stays runnable in CI on all three platforms.
- **Silent failure paths between components:** (a) `register_all_commands` returning `None`
  while `CliApplication.run` still binds the result — mypy strict catches it, and the
  full-tree help walk catches a runtime variant; (b) `_preconfigure` losing its return value
  while `run()` still tests it for `None` — caught by the invalid-root-syntax JSON cases;
  (c) `ApplicationContext.configure` losing the harness guard and thereby losing the
  idempotence short-circuit below it — caught by the `--json doctor` case, which configures
  twice (inspector, then Click callback) and must emit exactly one document.
- **Hidden assumptions only integration surfaces:** that Click's `NoSuchCommand` for a removed
  group produces the same code and status as for a never-existing one; that the packaged
  wheel contains no orphaned `harnesses` subpackage (`setuptools.packages.find` discovers
  packages by directory, so a stale directory would ship silently) — the existing
  `run_ci.py` clean-wheel install plus a `python -c "import vidbyte_cli.harnesses"` failure
  assertion covers it.

### Manual / QA Test Cases

1. Given a clean checkout on the feature branch, when I run `python -m pip install -e ".[dev]"`
   then `vidbyte-cli --help`, then the listing shows exactly `config`, `doctor`, `login`,
   `logout`, `research`, `whoami` and no other command — [Edge Case: the empty-state first
   impression this whole change exists to fix].
2. Given the CLI installed, when I run `vidbyte-cli harness catalog`, then it exits 2 with
   `Error [INVALID_ARGUMENT]` and a "no such command" message rather than
   `Error [NOT_IMPLEMENTED]` — [Hidden Assumption: that removal is indistinguishable from
   never having existed].
3. Given a logged-in profile with a `research:read` key, when I run
   `vidbyte-cli research threads`, then it prints the portfolio unchanged from `main` —
   [Silent Failure: proving the deletion did not disturb the live surface].
4. Given no stored credential, when I run `vidbyte-cli research thread <valid-uuid>`, then it
   exits 4 with `AUTH_REQUIRED`; when I run `vidbyte-cli research thread not-a-token`, it
   exits 2 with `INVALID_ARGUMENT` — [Edge Case: the ordering of local validation against
   credential resolution].
5. Given `VIDBYTE_API_URL` pointed at an unreachable host, when I run `vidbyte-cli --help`,
   then it exits 0 immediately with no network delay — [Hidden Failure: help must stay
   offline now that the pass that used to be the network risk is gone].
6. Given the built wheel from `run_ci.py`, when I run
   `python -c "import vidbyte_cli.harnesses"` inside the clean install venv, then it raises
   `ModuleNotFoundError` — [Hidden Failure: a stale directory shipping in the distribution].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
| --- | --- | --- | --- |
| `click` | `>=8.1,<9` | Command tree; unchanged | None — usage shrinks |
| `httpx` | `>=0.27,<1` | Transport; unchanged | None |
| `pydantic` | `>=2.6,<3` | Wire models; two modules deleted | None |
| `keyring` | `>=25.2,<26` | Credential store; untouched | None |
| `platformdirs` | `>=4.4,<5` | State roots; the manifest cache dir is no longer used | None — stale dirs are inert |
| Vidbyte API | `/api/v1/research/*`, `/api/skills/auth/validate` | The only routes called after this change | None — call set shrinks |
| Vidbyte API | `/harness/*` | Removed | **Eliminated** — these were never served |

No dependency is added, removed, or version-bumped.

---

## 12. Rollout & Deployment

- **Feature flags:** none. This repository has no flag mechanism, and the change is a pure
  removal of unreachable behavior — a flag would preserve a menu that cannot work, which is
  the defect.
- **Breaking change:** yes, nominally — `vidbyte-cli harness ...` and
  `vidbyte-cli connect github` stop being recognized commands. The practical impact is nil:
  every one of them raised `NOT_IMPLEMENTED` on `main`, so no caller can have a working script
  that depends on them. Any script that *did* invoke them was already failing, and its exit
  status changes from 1 (`OPERATIONAL_FAILURE`) to 2 (`USAGE`).
- **Migration path:** none required. No stored state format changes. A stale manifest cache
  directory from an earlier install is left in place and simply never read.
- **Deployment order:** single repository, single PR into `main`. No backend coordination —
  this change removes calls, it does not add any.
- **Rollback:** `git revert` of the merge commit restores the entire surface; every deleted
  file is intact in history at `915e8a7`. No data migration means rollback is unconditional.
- **Version:** `pyproject.toml` stays at `0.1.0`; the package is unpublished, so there is no
  released consumer to signal.

---

## 13. Open Questions

- [ ] Should `CliErrorCode.NOT_IMPLEMENTED` be retired now that nothing can emit it? This doc
      keeps it (§14, Alternative 3). The counter-argument — an enum value no code can produce
      is a lie in a published contract — is real, and retiring it would be a one-line follow-up
      once we are confident no external agent matches on it.
- [ ] Is `PromptInputResolver` (`lib/io/prompt.py`) wanted? It is exported from `lib/io` and
      has no consumer in `src/`, and seven `CliError` subclasses exist only to serve it. It was
      already dead before this change, so it is deliberately out of scope — but it is the next
      obvious cleanup, and it would remove ~200 lines.
- [ ] Same question for `ApiEnvelope`/`ApiError`/`ApiPagination` in `types/api.py` and the
      `ResponseShape.ENVELOPE` branch. Keeping them assumes a future non-research API-key route
      will arrive; if research is the whole product, they should go too.
- [ ] Confirm nobody is depending on `.claude/skills/add-harness/` before deleting it. It is a
      repo-local agent skill, not a published artifact, so this is expected to be a formality.

---

## 14. Alternatives Considered

### Alternative 1: Hide the commands with `hidden=True` instead of deleting them

- **What:** Pass `hidden=True` to the `harness` and `connect` Click groups so they vanish from
  `--help` while remaining invocable, preserving the runtime for when `/harness/*` ships.
- **Why rejected:** It satisfies the letter of the ask and none of its intent. A hidden command
  that raises `NOT_IMPLEMENTED` is still a trap for anyone who finds it in a changelog, a blog
  post, or an older README — and worse, it keeps ~1,400 lines of runtime alive that no test
  exercises and no reviewer has reason to read. Deletion is reversible in one `git revert`;
  dead code preserved "for later" is paid for on every read, every refactor, and every strict
  mypy run, and the `/harness/*` routes may never be built in the shape this runtime assumes.

### Alternative 2: Mark the commands "coming soon" in help text

- **What:** Keep the commands, retitle them `(not yet available)`, and keep the
  `NotImplementedFeature` failure.
- **Why rejected:** This is what `main` effectively already does, and it is the reported
  problem. The stated done condition is that a new user who types `--help` sees only actions
  that work tonight; a "coming soon" entry is still an entry, and it costs a user one failed
  invocation to learn nothing.

### Alternative 3: Also remove `CliErrorCode.NOT_IMPLEMENTED`

- **What:** Delete the enum member alongside the `NotImplementedFeature` class.
- **Why rejected (for now):** `lib/errors/codes.py` opens with "Every value here is a public
  contract: a shipped code string may not be reworded and a shipped exit number may not be
  reassigned." Removing a member is a stronger break than rewording one, and the machine error
  envelope is explicitly documented as an automation contract that agents branch on. Keeping
  one unemittable member costs a single line; breaking a consumer's `match` costs more.
  **Condition that flips it:** if we confirm no external consumer exists (the package is
  unpublished, so this is likely), retire it in a follow-up.

### Alternative 4: Delete `RootOptionInspector` along with the attachment pass

- **What:** The inspector's module docstring frames it entirely as harness-driven — "Click
  needs a harness namespace to exist before it dispatches" — which reads like it should go too.
- **Why rejected:** It has a second, load-bearing job the docstring buries: `--format` and
  `--debug` must take effect *before* Click parses, because Click's own syntax errors leave
  through `ErrorHandler`, and without the pre-scan those errors would render as human text
  even when the caller asked for JSON. `smoke.py` already asserts this
  (`--format json --not-an-option` must produce a machine error document). Deleting the
  inspector would break requirement 8 silently — the invocation still fails with the right
  code, just in the wrong encoding, which is exactly the class of regression a test suite
  built around exit codes would miss.

### Alternative 5: Keep `ApiClient.get_list` and `ResponseDecoder.many` for future routes

- **What:** Leave the collection-decoding path in place; some later API-key route will return
  an enveloped list.
- **Why rejected:** Neither has a caller after this change, and both are the enveloped-list
  path specifically — the research portfolio returns a *direct* `{threads, next_cursor}` DTO,
  not an envelope, so the surviving read surface would not use them even if it grew. Restoring
  fourteen lines when a route actually needs them is cheaper than carrying an untested decode
  path that only strict mypy ever looks at. `ResponseShape.ENVELOPE` and `_unwrap` are kept
  because they remain the declared default for `get`/`post` and are not orphaned by this
  change — the asymmetry is deliberate.
