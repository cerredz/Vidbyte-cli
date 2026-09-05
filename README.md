# Vidbyte CLI

Vidbyte runtime primitives are designed to execute through the user's installed coding
agent, preserving its repository, tools, skills, permissions, and model subscription. The
current runtime scaffold performs discovery and validation only; it does not charge or
launch sub-agents yet.

The Vidbyte CLI: authenticate, run Vidbyte research threads, and manage configuration.
Research executes entirely on the Vidbyte backend — this CLI admits runs, reads their durable
status, and lists the threads you own.

> **Status:** every command listed below works against the live API today. The CLI ships a
> command only once the backend route behind it is live, so nothing here can answer "not
> implemented yet". Deep dives, artifact bodies, sources, and exports live on the website
> only; they have no API-key route, so they have no command.

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

Root options precede the command: `vidbyte-cli --format json --profile work research threads`.

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
| `vidbyte-cli research start <prompt>` | Open a research thread and admit its first run |
| `vidbyte-cli research add <thread_id> <prompt>` | Add another run to an existing thread |
| `vidbyte-cli research resume <run_id>` | Continue a partial, failed, or out-of-credit run |
| `vidbyte-cli research status <run_id>` | Show one run's current status |
| `vidbyte-cli research watch <run_id>` | Follow one run until it settles |
| `vidbyte-cli research threads` | List your research threads |
| `vidbyte-cli research thread <thread_id>` | Show one thread and its rollup counters |
| `vidbyte-cli runtime list` | List local runtime primitives and admission prices |
| `vidbyte-cli runtime doctor` | Detect supported native coding-agent hosts |
| `vidbyte-cli runtime adversarial-team <task>` | Validate the first local primitive launch (executor not yet implemented) |
| `vidbyte-cli runtime same-host-ensemble <task>` | Run a role-differentiated agent ensemble on this machine |
| `vidbyte-cli config get\|set` | Manage CLI configuration |
| `vidbyte-cli doctor` | Diagnose CLI setup |

### Research threads

A thread is addressed only by the public ID that `research start` and `research threads`
print. That is the value to pass back to `research add` and `research thread`; the internal
identifier some other tools show is rejected before a request is sent.

`research status` and `research watch` report state, phase, continuation count, and a
timestamp — the whole of what the API publishes for a run. Neither prints a thread ID,
because the status route does not carry a usable one.

Starting, adding, and resuming are priced and idempotent. Each sends a generated
`Idempotency-Key` and reports it, so `--idempotency-key <that value>` retries a mutation
whose outcome you did not see without paying for it twice. `research watch` polls every ten
seconds and backs off from there: API keys are metered on a weighted per-minute budget, and
polling harder can exhaust the budget you need to start the next run.

### Local runtime primitives

`runtime` commands execute on your machine, driving a native coding agent you already
installed. Vidbyte charges a small flat admission fee for the orchestration; the model usage
runs against your own provider subscription, not ours.

Install the extra first — it is not part of the base package:

```bash
pip install "vidbyte-cli[codex]"
```

`runtime same-host-ensemble <task>` runs four stages on one machine. A planner agent reads
your task and generates the ensemble's roles, writing each role's complete system prompt
rather than picking from a fixed list, so the perspectives match the task. Each role then runs
concurrently in its own read-only fork and returns 5 to 10 distinct approaches, each with its
pros, cons, risks, and the files it would touch. A role cannot edit anything — the sandbox
forbids it, not just the prompt. A selector fork then narrows every approach from every role
down to one, in rounds: each round keeps a fifth of what it was given, weighs the pros and
cons of every candidate it keeps, and records why the rest were dropped. Finally one
write-enabled fork receives the selected approach and the selector's brief, and does the work.
That last fork is the only agent in the topology permitted to modify your workspace.

| Option | Default | Meaning |
|--------|---------|---------|
| `--host` | `codex` | Native host. Codex is the only one with verified fork and sandbox support. |
| `--roles` | `3` | How many roles the planner generates, 3 to 100. |
| `--model` | provider default | Model override passed through to the host. |
| `--reasoning-effort` | provider default | One of `none`, `minimal`, `low`, `medium`, `high`, `xhigh`. |
| `--role-timeout` | `300` | Seconds one role may take before it is recorded as failed. |

A role that times out or fails is reported in the result and the run continues, because a
partial ensemble still beats a single agent. The run stops only when every role failed.

Two costs are worth separating. Admission is two cents, charged once, after the CLI has
confirmed your input, the SDK, and the host — so a missing Codex never costs you anything.
The larger cost is your own provider usage: the SDK opens a fresh Codex app-server per turn
and per fork, so a three-role run is roughly a dozen of them against your subscription, and
`--roles 100` is a thousand approaches for the selector to read. Raise it deliberately.

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

Local runtimes are separate from hosted harnesses. Vidbyte authenticates a launch and will
charge a flat admission fee from the API-key wallet, while Codex, Claude Code, or OpenCode
executes locally using the user's own account. x402 funds that wallet through the backend's
`POST /agent/topup` route; machine environment and repository contents are never uploaded
for admission.

Every command is static and known at release time. Runtime discovery adds one authenticated
catalog route, while the paid admission operation is typed but deliberately unreachable from
this scaffold. See
[docs/architecture.md](docs/architecture.md) for the layering rules and the full
[backend contract](docs/architecture.md#backend-contract).

The application composition root lives in `src/vidbyte_cli/lib/runtime`. It constructs one
invocation context, binds stdin/stdout/stderr through `lib/io`, resolves output and error
policy, and builds the Click tree.

## Verify

```bash
python -m pip install -e ".[dev]"
python scripts/run_ci.py
```

The canonical gate runs Ruff lint/format checks, strict mypy, byte compilation, offline
command smoke checks, sdist/wheel build, Twine metadata validation, and an installed-wheel
smoke check. GitHub Actions invokes the same script on Linux, Windows, and macOS.

## Follow-ups

- Deep dives have no API-key route. `POST /api/research/threads/{id}/artifacts/{id}/deep` is
  session-only, and no API-key read publishes an artifact identifier to address, so a CLI
  command needs three backend routes rather than one: list a thread's artifacts, admit the
  deep dive, and read its result. Until those ship, deep dives stay on the website.
- `research start/add/resume` could take `--wait` to block after admission, and the research
  reads could take `--exit-status` to map a terminal outcome onto the shell status. The
  latter needs `CliApplication._invoke` to stop discarding a command's return value.
- Credential verification uses the backend's permission-free liveness check, which allows only
  a few authentication attempts per address per quarter hour. A read-only identity route with
  no such budget would suit `whoami` better; see `docs/design/login-key-verification.md` §14.
- The console command is `vidbyte-cli` (not `vidbyte`) to avoid the bin/name collision with
  the `vidbyte-skills` package; confirm before publishing.
- Confirm the production API host.
