# Vidbyte CLI

Vidbyte persistence runs one session through the installed Codex CLI, using an OpenAI
BYOK key and the current working directory. It verifies a two-cent Vidbyte admission
before starting the agent. Other runtime executors remain scaffolds.

The Vidbyte CLI: authenticate, run Vidbyte research threads, and manage configuration.
Research executes entirely on the Vidbyte backend — this CLI admits runs, reads their durable
status, and lists the threads you own.

> **Status:** persistence requires a backend deployment with persistence activation and
> grant verification. Adversarial-team still has no executor. Deep dives, artifact bodies,
> sources, and exports remain website-only.

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
| `vidbyte-cli runtime persistence <task> [--strength 1-6]` | Run one Codex session with 6–100 additional improvement turns |
| `vidbyte-cli config get\|set` | Manage CLI configuration |
| `vidbyte-cli doctor` | Diagnose CLI setup |
| `vidbyte-cli connections login <github\|slack\|google\|google-drive>` | Connect a context provider account |
| `vidbyte-cli connections list\|status\|logout` | Inspect or remove named context connections |
| `vidbyte-cli connections read ...` | Read one bounded repository, channel, or Drive file |

### Context-provider connections

Context-provider connections are separate from model-provider API keys. Configure one OAuth
application per service before logging in:

```powershell
# GitHub OAuth App: enable Device Flow in the app settings.
$env:VIDBYTE_GITHUB_CLIENT_ID = "..."

# Slack app: enable PKCE and configure the user history scopes in OAuth & Permissions.
$env:VIDBYTE_SLACK_CLIENT_ID = "..."

# Google Cloud: enable Drive API, create a Desktop OAuth client, and download its JSON.
$env:VIDBYTE_GOOGLE_CLIENT_SECRETS = "C:\path\client_secret.json"
```

On macOS/Linux, use the equivalent `export NAME=value` commands. The GitHub and Slack client
IDs are public application identifiers; Slack PKCE does not use a client secret. Google reads
the standard `installed` client JSON only. The default Google `drive.readonly` scope may require
adding the account as a test user during development and completing Google's verification before
shipping to a wider audience.

Then authenticate and verify access:

```bash
vidbyte-cli connections login github --name work-github
vidbyte-cli connections login slack --name work-slack
vidbyte-cli connections login google-drive --name work-drive
vidbyte-cli connections list
vidbyte-cli connections status work-github
vidbyte-cli connections read github repo acme/api --connection work-github
vidbyte-cli connections read slack channel C123456 --connection work-slack --limit 25
vidbyte-cli connections read google-drive file FILE_ID --connection work-drive
```

OAuth access and refresh tokens are stored in the operating system keyring under the dedicated
Vidbyte connection service. The local metadata file contains account labels and scopes only.
GitHub device flow is documented by GitHub, Google uses a loopback callback with PKCE, and
Slack requires PKCE to be enabled for localhost desktop redirects. `drive.readonly` is the
default Google scope so arbitrary readable document IDs can be fetched; Google may require
application verification for that restricted scope.

`google` is accepted as a shorthand for the canonical `google-drive` provider name.

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
| `--host` | `codex` | Which installed coding agent hosts the ensemble. Codex is the only host with verified thread-fork and per-fork sandbox support, so it is the only accepted value. |
| `--roles` | `3` | How many specialist roles the planner invents for this task (3-100). More roles widen the approach slate the selector narrows; every role runs concurrently in its own read-only fork against your subscription. |
| `--model` | provider default | Model override forwarded to every Codex turn and fork in the run. Omit to use the provider default. |
| `--reasoning-effort` | provider default | Reasoning effort forwarded to every Codex turn in the run (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`). Omit to use the provider default. |
| `--idempotency-key` | generated | Reuse a key to retry a priced admission without being charged twice. Omit to generate one per invocation. |

A role that times out (after a fixed 300-second bound) or fails is reported in the result
and the run continues, because a partial ensemble still beats a single agent. The run
stops only when every role failed.

Two costs are worth separating. Admission is two cents, charged once, after the CLI has
confirmed your input, the SDK, and the host — so a missing Codex never costs you anything.
The grant is then verified through the layered runtime gate before any agent starts; a
rejected grant fails the run without starting a single fork. The larger cost is your own
provider usage: the SDK opens a fresh Codex app-server per turn
and per fork, so a three-role run is roughly a dozen of them against your subscription, and
`--roles 100` is a thousand approaches for the selector to read. Raise it deliberately.

### Persistent Codex agent

```bash
vidbyte-cli login
vidbyte-cli provider login openai
vidbyte-cli runtime persistence "Your exact task" --strength 1
```

Install Codex on PATH first. Persistence uses the Vidbyte SDK's `CodexHarnessAgent`;
installation pins the SDK source revision with the required Codex integration and
requires Git to fetch it. OpenAI credentials resolve from `OPENAI_API_KEY`, then the
selected profile's keyring or approved file fallback. They are passed only to the Codex
child, using its Responses API provider configuration; native Codex login is unchanged.
The configured Codex model must be available to that OpenAI API key.

Strength tiers 1–6 send **6, 8, 20, 40, 70, 100 additional turns**, after the exact original
task. Every follow-up includes encouragement and the exact original task. All turns resume
the same explicit session ID. `--host auto` selects Codex; other hosts are unsupported.
Codex runs with workspace-write sandboxing, without a sandbox bypass.

Each invocation costs two cents from the Vidbyte API wallet, plus your OpenAI usage.
Grant verification is authenticated and checks signature, caller identity, request binding,
capability, price and expiry. No signing secret is distributed to the CLI. Task text and
provider credentials never enter Vidbyte admission requests.

Use a caller-chosen `--idempotency-key` (8–128 allowed characters) to recover an uncertain
admission request without another debit. Reusing it does not resume local work: a new CLI
invocation starts a new Codex session, so do not rerun a completed task with a recovery key.
Ctrl+C cancels the active SDK turn and closes its Codex connection.
A failed or hour-long turn stops the loop;
completed local work remains, and the flat admission fee is not automatically refunded.
This is a foreground loop, not a daemon that survives terminal closure.

Only the final response is written to stdout; progress goes to stderr. Updates explain
preparation, admission, the initial task, and subsequent improvement phases without
displaying loop indices. JSON output includes
`session_id`, `continuation_turns`, and `text` in the standard result envelope.

## Configuration

| Variable | Meaning |
| --- | --- |
| `VIDBYTE_API_URL` | API host (default `https://vidbyte-backend.onrender.com`) |
| `VIDBYTE_API_KEY` | API key; overrides the stored credential for the current shell |
| `VIDBYTE_PROFILE` | Profile name; the lower-precedence equivalent of `--profile` |
| `VIDBYTE_OUTPUT_FORMAT` / `VIDBYTE_COLOR` | Presentation defaults |
| `VIDBYTE_REQUEST_TIMEOUT_SECONDS` | Per-request timeout |
| `VIDBYTE_GITHUB_CLIENT_ID` / `VIDBYTE_GITHUB_CLIENT_SECRET` | GitHub OAuth App client settings |
| `VIDBYTE_SLACK_CLIENT_ID` | Slack PKCE public-app client ID |
| `VIDBYTE_GOOGLE_CLIENT_SECRETS` | Path to a Google installed-app client JSON |

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

Local runtimes are separate from hosted harnesses. Vidbyte authenticates a launch and
charges a flat admission fee from the API-key wallet, while persistence executes in Codex
using the caller's OpenAI API key. x402 funds that wallet through the backend's
`POST /agent/topup` route; machine environment and repository contents are never uploaded
for admission.

Every command is static and known at release time. Runtime discovery adds one authenticated
catalog route. Persistence calls activation and authenticated grant verification before
launching Codex. See
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


### Runtime admission payments

`vidbyte-cli runtime persistence "your task"` uses your authenticated Vidbyte API
balance by default. The flat $0.02 admission is recorded as ordinary API usage.
Local Codex model usage is still paid through your OpenAI credentials.

To pay the admission directly with x402, set `VIDBYTE_X402_PRIVATE_KEY` in your
shell and run `vidbyte-cli runtime persistence "your task" --with-x402-payment`.
A Vidbyte API key with `runtime:write` is required for ownership in both modes.
`VIDBYTE_X402_NETWORK` defaults to Base (`eip155:8453`); Base Sepolia
(`eip155:84532`) is supported for testing. Keep private keys out of command arguments.
The wallet must already hold the network's USDC; the CLI does not fund it.

Both modes verify the signed receipt against Vidbyte's database before launching
Codex. The API-balance path also verifies the exact usage-ledger debit. Payment
credentials are not passed to Codex. The CLI never switches payment methods automatically.
Recover a failed admission with the same `--idempotency-key`; a retry preserves the
original grant and expiry. An uncertain payment outcome must be reconciled before
starting another purchase. Verification does not refund a failed local execution.
