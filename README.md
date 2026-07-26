# Vidbyte CLI

The universal Vidbyte CLI: authenticate, run Vidbyte harnesses against your repositories,
and manage configuration. Harnesses execute entirely on the Vidbyte backend — this CLI
submits runs, tracks status, and retrieves results (branch / draft PR).

> **Status:** Python platform scaffold. Commands that have not reached their implementation
> PR return a typed "not implemented yet" error. Executable lifecycle, injected process I/O,
> human/machine output, safe error handling, package versioning, and CI are production-shaped.

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

Root options precede the command, for example
`vidbyte-cli --format json --profile work harness list`.

| Option | Behavior |
| --- | --- |
| `--format human\|json\|jsonl\|none` | Select human, one-document, streaming, or suppressed result output |
| `--json` | Alias for `--format json`; conflicts with any non-JSON `--format` |
| `--profile NAME` | Select a configuration profile (storage and precedence land in PR 3) |
| `--no-input` | Prevent interactive prompting |
| `--color auto\|always\|never` | Select color preference subject to terminal safety |
| `--debug` | Show redacted stack frames without exception values or locals |

Successful command results are the only content written to stdout. Progress, warnings,
diagnostics, and errors use stderr. JSON and JSONL documents include `schema_version` and
`kind`; machine errors use the same versioned envelope on stderr.

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
| `VIDBYTE_API_URL` | API host (default `https://api.vidbyte.ai`) |
| `VIDBYTE_API_KEY` | API key; overrides the stored credential for the current shell |

State lives under `~/.vidbyte/` (`credentials.json`, `config.json`, `manifests/`).

## Architecture

Each harness is effectively its own sub-CLI: `vidbyte-cli harness <name> <command> ...`,
with the commands described by a backend manifest and built at runtime, so new harnesses
need no CLI release. See [docs/architecture.md](docs/architecture.md) for the layering
rules and [how to integrate a harness](docs/architecture.md#integrating-a-harness-in-srcvidbyte_cliharnessesname).

The application composition root lives in `src/vidbyte_cli/lib/runtime`. It constructs one
invocation context, binds stdin/stdout/stderr through `lib/io`, builds the static Click tree,
configures output/error policy, and attaches only the requested dynamic harness namespace.

## Verify

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

The canonical gate runs Ruff lint/format checks, strict mypy, byte compilation, offline
command smoke checks, sdist/wheel build, Twine metadata validation, and an installed-wheel
smoke check. GitHub Actions invokes the same script on Linux, Windows, and macOS.

## Follow-ups

- Implement the stores, `ApiClient` requests, the catalog fetch/cache, and the
  `harness run/status/list` behavior once the backend routes ship.
- The console command is `vidbyte-cli` (not `vidbyte`) to avoid the bin/name collision with
  the `vidbyte-skills` package; confirm before publishing.
- Confirm the production API host.
