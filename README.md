# Vidbyte CLI

The universal Vidbyte CLI: authenticate, run Vidbyte harnesses against your repositories,
and manage configuration. Harnesses execute entirely on the Vidbyte backend — this CLI
submits runs, tracks status, and retrieves results (branch / draft PR).

> **Status:** scaffold. Every command parses its arguments fully, then exits `1` with a
> clear "not implemented yet" message. The command surface, layering, types, and the
> harness runtime are in place so they can be reviewed before behavior lands.

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
vidbyte-cli --help
```

The console command is `vidbyte-cli`.

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

## Verify

```bash
python -m compileall src     # compiles clean
python scripts/smoke.py      # boots the CLI and renders every help screen
```

## Follow-ups

- Implement the stores, `ApiClient` requests, the catalog fetch/cache, and the
  `harness run/status/list` behavior once the backend routes ship.
- The console command is `vidbyte-cli` (not `vidbyte`) to avoid the bin/name collision with
  the `vidbyte-skills` package; confirm before publishing.
- Confirm the production API host.
