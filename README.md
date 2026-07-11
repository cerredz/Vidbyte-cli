# Vidbyte CLI

The universal command-line client for the Vidbyte platform: authentication, harness runs,
and configuration. Harnesses (like the software-engineering harness) execute entirely on
the Vidbyte backend; this CLI submits runs, tracks their status, and retrieves results.

> **Status: scaffold.** Command surfaces parse and dispatch, but behaviors are stubbed and
> exit with a "not implemented yet" message. The backend `/harness/*` routes this CLI
> targets are being built in parallel.

## Install

```bash
npm install -g vidbyte-cli   # not yet published to npm
# or from source:
git clone https://github.com/cerredz/Vidbyte-cli.git && cd Vidbyte-cli
npm install && npm run build
node bin/vidbyte.js --help
```

Requires Node.js >= 18.

## Quickstart

```bash
vidbyte login                     # store your Vidbyte API key
vidbyte connect github            # let harnesses clone your repos and open PRs
cd your-project
vidbyte harness run software-engineering --task "Fix the duplicate invoice bug"
vidbyte harness status <run_id>   # status, event log, resulting branch / draft PR
```

Agent environments (Claude Code, Codex, etc.) can invoke the same commands via their
shell tools — the CLI is the integration surface.

## Commands

| Command | Purpose |
|---------|---------|
| `vidbyte login` / `logout` / `whoami` | Manage the stored Vidbyte API key |
| `vidbyte connect github` | Link GitHub for harness repository access |
| `vidbyte harness run <name> --task <task>` | Submit a harness run for the current repo |
| `vidbyte harness status <run_id>` | Show a run's status, events, and result |
| `vidbyte harness list` | List your runs |
| `vidbyte config get\|set` | Manage CLI settings (`~/.vidbyte/config.json`) |
| `vidbyte doctor` | Diagnose environment, credentials, and connectivity |

## Architecture

Strict layering — see [docs/architecture.md](docs/architecture.md):

```text
src/commands/   thin: parse args → call lib services → render output
src/lib/api/    ApiClient (base URL, auth header, envelope) + typed endpoint groups
src/lib/auth/   credential store (~/.vidbyte/credentials.json)
src/lib/config/ config store + single source of truth for ~/.vidbyte paths
src/lib/git/    local repository introspection (origin, sha, branch, dirty)
src/lib/output/ logger + renderers
src/lib/errors/ CliError with exit codes; index.ts owns the central trap
src/types/      API envelope + resource types mirroring backend DTOs
```

## Development

```bash
npm install
npm run build    # tsc → dist/
npm run smoke    # build + `vidbyte --help` sanity check
```

Configuration for local development lives in `.env` (see `.env.example`):
`VIDBYTE_API_URL` overrides the API host, `VIDBYTE_API_KEY` bypasses the credential store.

## License

MIT
