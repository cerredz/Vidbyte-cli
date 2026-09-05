# Vidbyte CLI

The Vidbyte CLI (`vidbyte-cli`) is the terminal client for Vidbyte research. It authenticates against the Vidbyte API, opens and continues research threads, reads their durable status, and manages local configuration. Research itself executes entirely on the Vidbyte backend — this CLI admits runs, polls their state, and lists the threads you own. It ships a command only once the backend route behind it is live, so nothing in its surface can answer "not implemented yet"; deep dives, artifact bodies, sources, and exports live on the website only, have no API-key route, and therefore have no command.

Two contracts shape almost every file here. First, **results are the only thing on stdout** — progress, warnings, diagnostics, and errors go to stderr — and JSON/JSONL records carry `schema_version` and `kind`, with machine errors using the same envelope plus `description`, `trace`, and `file_path` so an agent invoking this CLI can diagnose and correct its own call. Second, **the reusable Python entry function returns an integer status**; only the generated console wrapper and `python -m vidbyte_cli` terminate a process. This is the smallest repository in the Vidbyte workspace at 94 tracked files, and it is intentionally thin: it is a transport and presentation layer over a remote API, not a place where research logic lives.

> **This file is a Map.** It is a lossy compression of what this repository already contains in full — folder topology and what each folder is for, nothing that isn't derivable from the tree itself. It exists to answer *where do I look next*, not to be correct in every detail. It is expected to drift; regenerate it rather than patching it.

## File Index

**Root files:** `README.md` — the command reference and the authority on CLI behavior, including global options, the output contract, and the idempotency rules for priced mutations. `pyproject.toml` — packaging, dependencies, the `[dev]` extra, and the `vidbyte-cli` console script entry point. `.env.example` — the environment variables the CLI reads. `LICENSE`, `.gitignore`.

### `.github/`

GitHub Actions configuration, and nothing else — this repository has no issue templates or other GitHub-side assets. Everything here runs remotely rather than in the package, so nothing in it ships in the wheel. Changing anything under it changes the remote gate and must be matched by the local gate in `scripts/run_ci.py`.

#### `.github/workflows/`

A single `ci.yml`, whose header states the rule the repository is built around: the workflow is *the OS/Python matrix only*, and every verification step lives in `scripts/run_ci.py` so local and remote gates cannot drift. Nothing may inline lint or build commands here, and nothing may publish packages here. The matrix covers Ubuntu on Python 3.11 and 3.14, plus Windows and macOS on 3.11, and runs on every pull request and every push to `main` with no path filter.

### `docs/`

Design documentation for the CLI. Every non-trivial change lands a design doc here before implementation, so this folder doubles as the decision history: read it to find out why a command exists in the shape it does. It is the fastest route to why a command has the surface it does.

#### `docs/design/`

One Markdown design doc per feature. The set traces the CLI's evolution — `harness-runtime-and-cli-scaffold.md` (the original scaffold), `python-cli-research-harness-program.md`, `live-api-host-and-key-header.md` (how the CLI addresses the live API and passes credentials), `login-key-verification.md`, `research-only-command-surface.md` and `research-production-api-surface.md` (the decision to ship only commands the API can actually answer). Start here before changing a command's shape.

### `scripts/`

Verification entry points, kept outside the package so they never ship in the wheel. `run_ci.py` is the canonical gate — the single command both a developer and GitHub Actions run, covering lint, type checks, tests, distribution build, and a clean-install smoke check of the built wheel. `smoke.py` and the targeted `test_login_key_verification.py` and `test_research_only_surface.py` scripts diagnose individual areas, but they never substitute for a full `run_ci.py` pass. If you change anything in `src/`, this is what has to go green.

### `src/`

The packaging root. It holds exactly one package, `vidbyte_cli`, using the src-layout convention so tests and CI must exercise the *installed* package rather than accidentally importing from the working directory. Nothing else belongs at this level.

#### `src/vidbyte_cli/`

The CLI package itself. `cli.py` is the root parser and dispatcher — it owns the global options (`--format`, `--json`, `--profile`, `--no-input`, `--color`, `--debug`) that precede any command and returns an integer status rather than exiting. `__main__.py` is the `python -m vidbyte_cli` wrapper, one of only two places allowed to terminate the process. `README.md` documents the package's internal layering for contributors.

##### `src/vidbyte_cli/commands/`

One subpackage per command family, each owning argument parsing and result rendering for its own verbs and nothing else. `auth/` implements `login`, `logout`, and `whoami` over the stored API key; `research/` implements `start`, `add`, `resume`, `status`, `watch`, `threads`, and `thread`; `config/` implements `get` and `set`; `setup/` implements `doctor`. Commands orchestrate — they call into `lib/` for transport, credentials, and formatting rather than doing that work themselves.

##### `src/vidbyte_cli/lib/`

The shared substrate every command depends on, and the largest part of the package at 48 files. `api/` is the HTTP client and route surface, including idempotency-key generation for priced mutations; `auth/` is credential storage, profile scoping, and header construction; `config/` resolves configuration across profiles, environment, and defaults; `errors/` defines the typed failure envelope carrying `description`, `trace`, and `file_path`; `io/` handles stdin and interactive prompting under `--no-input`; `output/` enforces the human/json/jsonl/none rendering contract and the stdout-is-results-only rule; `runtime/` holds process-level concerns such as color detection and redacted debug frames. The dependency direction is one-way: commands may import from `lib/`, but nothing in `lib/` may import a command.

##### `src/vidbyte_cli/services/`

Feature services: the layer between a command and the shared substrate. Each subfolder owns one product's algorithm from validated input to normalized result. `ensemble/` implements the `runtime same-host-ensemble` primitive — a planner turn that generates the role roster, concurrent read-only forks that each return a slate of weighed approaches, a read-only selector that narrows every approach to one across several rounds, and one write-enabled fork that implements the winner. Its `prompts/` subpackage holds every prompt as a Markdown file, so no Python file in the service contains a sentence addressed to a model. Its `sdk.py` is the only module in the package that imports `vidbyte-sdk`, and it does so lazily inside a method, because the published SDK release predates the Codex integration and `--help` must work without it. The dependency direction extends the one below: commands may import services, services may import `lib/`, and nothing in `lib/` may import a service.

##### `src/vidbyte_cli/types/`

Typed payload definitions shared between the API client and the commands that render its responses. `api.py` describes the request and response envelopes including `schema_version` and `kind`; `research.py` describes thread and run shapes — state, phase, continuation count, timestamp — that `status`, `watch`, `threads`, and `thread` print. Keeping these separate from `lib/api/` is what lets a command depend on the *shape* of a response without depending on the transport that fetched it.

### `skills/`

Agent-facing background for building runtime primitives, kept outside the package so nothing here ships in the wheel. `harnesses/runtime-primitives/` explains what a locally-executed primitive is and the seven parts every one shares; `harnesses/codex-harness-sdk/` covers driving the SDK's Codex agent, including four behaviors of its merged code that its own design doc does not describe, plus a `references/build-decisions.md` checklist of the ordered choices a new primitive requires; `harnesses/x402-runtime-economics/` covers admission, flat pricing, and why the backend catalog rather than the CLI owns a capability's route path. Read these before adding or changing a runtime primitive.

## Command Deck

This is the developer command reference for the repository's Python toolchain. It is deliberately **not** part of the Map's topology contract above, and it does not document package installation or end-user CLI usage. Run commands from the repository root with the development dependencies available.

### Fast feedback

- `python -m ruff check .`
  Runs the configured Ruff lint rules across the repository and reports import, style, and complexity violations.
  Params: add `--fix` to apply Ruff's safe automatic fixes.
- `python -m ruff format --check .`
  Verifies that Python files match the repository's Ruff formatter configuration without changing them.
  Params: use `python -m ruff format .` to apply formatting.
- `python -m mypy src`
  Runs strict mypy checks against the `vidbyte_cli` package configured in `pyproject.toml`.
  Params: `src` is the package root; keep this target aligned with the mypy configuration.
- `python -m compileall -q src`
  Byte-compiles the source tree to catch syntax and import-compilation failures quickly.
  Params: `-q` suppresses successful-file output.

### Targeted diagnostics

- `python scripts/smoke.py`
  Boots the public module entry point in isolated scratch state and checks command-tree startup, output streams, exit codes, and machine-error envelopes. It is offline and diagnostic; it does not replace the full gate.
  Params: none.
- `python scripts/test_login_key_verification.py`
  Runs the login verification checks against a loopback server, including the invariant that rejected credentials are never persisted.
  Params: none; it does not call the live API.
- `python scripts/test_research_only_surface.py`
  Checks that the authored command surface matches the API-backed research scope and that removed commands are not still importable or documented.
  Params: none.
- `python -m vidbyte_cli --help`
  Inspects the assembled command tree through the package entry point while debugging command registration or import-boundary changes.
  Params: add `--version` to check the package version path.
- `python -c "import vidbyte_cli; print(vidbyte_cli.__file__)"`
  Confirms which checkout or environment supplies the imported package, useful when an editable install or `PYTHONPATH` may be stale.
  Params: replace the expression only when diagnosing a specific import boundary.

### Packaging checks

- `python -m build --sdist --wheel --outdir dist`
  Builds the source distribution and wheel locally using the declared build-system requirements.
  Params: `--outdir dist` places artifacts in the repository's `dist/` directory.
- `python -m twine check dist/*`
  Validates the metadata and rendered descriptions of the distributions in `dist/`.
  Params: pass the artifact paths to limit validation to a selected build.
- `python scripts/run_ci.py`
  Runs the canonical local gate in the same order as GitHub Actions: lint, formatting, strict typing, byte compilation, targeted diagnostics, distribution build, Twine validation, and clean-wheel smoke checks.
  Params: none; this repository intentionally has one full gate and no stage selector.
