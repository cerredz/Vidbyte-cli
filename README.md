# Vidbyte CLI

The universal Vidbyte CLI: authenticate, run Vidbyte harnesses against your repositories,
and manage configuration. Harnesses execute entirely on the Vidbyte backend — this CLI
submits runs, tracks status, and retrieves results (branch / draft PR).

> **Status:** Python platform scaffold. Commands that have not reached their implementation
> PR still return a clear "not implemented yet" error, while the executable lifecycle,
> injected process I/O, package versioning, and canonical CI gate are production-shaped.

## Install (development)

```bash
python -m venv .venv
source .venv/bin/activate                          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
vidbyte-cli --help
```

The console command is `vidbyte-cli`. The reusable Python entry function returns an integer
status; only the generated console wrapper and `python -m vidbyte_cli` terminate a process.

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
and attaches only the requested dynamic harness namespace.

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
