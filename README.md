# Vidbyte CLI

The universal Vidbyte CLI: authenticate, run Vidbyte harnesses against your repositories,
and manage configuration. Harnesses execute entirely on the Vidbyte backend — this CLI
submits runs, tracks status, and retrieves results (branch / draft PR).

> **Status:** Python platform scaffold. Local configuration, profiles, platform paths,
> credential resolution, `config get`/`set`, `doctor`, and `logout` are implemented; login's
> verify-before-store HTTP seam and the other network commands land with the reusable HTTP
> platform. Commands that have not reached their implementation PR return a typed "not
> implemented yet" error.

## Install (development)

```bash
python -m venv .venv
source .venv/bin/activate                          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
vidbyte-cli --help
```

The console command is `vidbyte-cli`. The reusable Python entry function returns an integer
status; only the generated console wrapper and `python -m vidbyte_cli` terminate a process.

## Global options

Root options precede the command: `vidbyte-cli --format json --profile work harness list`.

| Option | Behavior |
| --- | --- |
| `--format human\|json\|jsonl\|none` | Human, one-document, streaming, or suppressed results |
| `--json` | Alias for `--format json`; conflicts with any other `--format` value |
| `--profile NAME` | Select a configuration and credential scope |
| `--no-input` | Never prompt for interactive input |
| `--color auto\|always\|never` | Color preference, subject to terminal safety |
| `--debug` | Show redacted stack frames — never exception values, causes, or locals |

Results are the only thing written to stdout; progress, warnings, diagnostics, and errors go
to stderr. JSON and JSONL records carry `schema_version` and `kind`, and machine errors use
that same envelope.

Every error also carries `description`, `trace`, and `file_path` — non-sensitive fields that
let an agent calling this CLI diagnose and correct its own invocation.

## Commands

| Command | Purpose |
| --- | --- |
| `vidbyte-cli login` / `logout` / `whoami` | Manage the stored Vidbyte API key |
| `vidbyte-cli connect github` | Link GitHub for harness repository access |
| `vidbyte-cli harness run <name> --task <task>` | Low-level generic run for the current repo |
| `vidbyte-cli harness <name> <command> ...` | A harness's own commands (built from its manifest) |
| `vidbyte-cli harness status <run_id>` | Show a run's status, events, and result |
| `vidbyte-cli harness list` | List your runs |
| `vidbyte-cli harness catalog` | List the harnesses available to run |
| `vidbyte-cli config get\|set` | Manage CLI configuration |
| `vidbyte-cli doctor` | Diagnose CLI setup |

## Configuration

| Variable | Meaning |
| --- | --- |
| `VIDBYTE_API_URL` | API host (default `https://vidbyte-backend.onrender.com`) |
| `VIDBYTE_API_KEY` | API key; overrides the stored credential for the current shell |
| `VIDBYTE_PROFILE` | Profile name; the lower-precedence equivalent of `--profile` |
| `VIDBYTE_OUTPUT_FORMAT` / `VIDBYTE_COLOR` | Presentation defaults |
| `VIDBYTE_REQUEST_TIMEOUT_SECONDS` | Per-request timeout |

Non-secret settings resolve command option → environment → selected profile → default
profile → built-in, and `vidbyte-cli config get <key>` reports both the effective value and
which layer supplied it. `config set` accepts `api_url`, `output_format`, `color`, and
`request_timeout_seconds`.

API keys resolve separately: environment → OS keyring → permission-restricted file. An
environment key is never persisted, and the restricted file is used only with explicit
consent. Configuration, cache, state, and data live in the platform's standard application
directories; `~/.vidbyte/` is still read, and is copied across by a verified migration that
leaves the originals in place.

## Architecture

Each harness is effectively its own sub-CLI: `vidbyte-cli harness <name> <command> ...`,
with the commands described by a backend manifest and built at runtime, so new harnesses
need no CLI release. See [docs/architecture.md](docs/architecture.md) for the layering
rules and [how to integrate a harness](docs/architecture.md#integrating-a-harness-in-srcvidbyte_cliharnessesname).

The application composition root lives in `src/vidbyte_cli/lib/runtime`. It constructs one
invocation context, binds stdin/stdout/stderr through `lib/io`, resolves output and error
policy, builds the static Click tree, and attaches only the requested dynamic harness
namespace.

## Verify

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

The canonical gate runs Ruff lint/format checks, strict mypy, byte compilation, offline
command smoke checks, sdist/wheel build, Twine metadata validation, and an installed-wheel
smoke check. GitHub Actions invokes the same script on Linux, Windows, and macOS.

## Follow-ups

- Implement `ApiClient` requests, credential verification, the catalog fetch/cache, and the
  `harness run/status/list` behavior once the backend routes ship.
- The console command is `vidbyte-cli` (not `vidbyte`) to avoid the bin/name collision with
  the `vidbyte-skills` package; confirm before publishing.
- Confirm the production API host.
