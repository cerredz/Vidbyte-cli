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

##### `src/vidbyte_cli/types/`

Typed payload definitions shared between the API client and the commands that render its responses. `api.py` describes the request and response envelopes including `schema_version` and `kind`; `research.py` describes thread and run shapes — state, phase, continuation count, timestamp — that `status`, `watch`, `threads`, and `thread` print. Keeping these separate from `lib/api/` is what lets a command depend on the *shape* of a response without depending on the transport that fetched it.
