# Vidbyte CLI Architecture

The CLI is a thin, typed client for the Vidbyte research harness. Research runs entirely on
the Vidbyte backend; the CLI authenticates, admits runs, and reads their durable status. It is
written in Python (click + pydantic + httpx).

Every command is static and known at release time, and a command exists here only when a
shipped backend route can answer it. That rule is the one this document is really about: a
command that parses successfully and then reports "not implemented" teaches a user that the
CLI is broken, which is worse than not shipping it.

## The layers

```text
pyproject.toml [project.scripts]   console entry `vidbyte-cli` -> vidbyte_cli.cli:main
src/vidbyte_cli/cli.py             thin reusable entry function returning an integer status
src/vidbyte_cli/__main__.py        outer `python -m` SystemExit boundary
src/vidbyte_cli/lib/runtime/       invocation composition, version, dispatch, error trap
                                   + the root-option pre-scan that settles output policy
src/vidbyte_cli/lib/io/            injected streams, terminal capabilities, prompt input
src/vidbyte_cli/commands/<group>/  one class per command: register() + execute()
src/vidbyte_cli/lib/api/client.py  ApiClient: base URL, API-key header, envelope unwrapping
src/vidbyte_cli/lib/api/endpoints/ typed endpoint groups (research, auth) on ApiClient
src/vidbyte_cli/lib/auth/          scoped env/keyring/restricted-file credential boundary
src/vidbyte_cli/lib/config/        typed profiles, provenance, native paths, safe migration
src/vidbyte_cli/lib/output/        versioned documents + the invocation's output manager
src/vidbyte_cli/lib/errors/        stable codes, CliError metadata, one central handler
src/vidbyte_cli/lib/runtime_primitives/ local host discovery, planning, executor seam
src/vidbyte_cli/types/             wire models mirroring backend DTOs
```

## Rules

1. **Commands are thin.** A command class parses arguments, calls lib services, and hands
   results to a renderer. Commands never call httpx, touch the filesystem stores, or call
   `sys.exit` directly.
2. **All HTTP goes through `ApiClient`** via a typed endpoint group. New backend surfaces
   get a new file in `lib/api/endpoints/`, never inline requests.
3. **Errors are raised, not printed.** Anything user-facing raises a `CliError` subclass from
   `lib/errors/failures.py`; `ErrorHandler` renders it and returns a status. Unexpected
   errors return 70 without exposing the exception value. `--debug` adds frames only.
4. **Secrets never log.** The API key may not appear in log lines, error messages, or
   rendered output.
5. **Paths have one source of truth.** Platform-native config/cache/state/data and the
   legacy `~/.vidbyte` compatibility locations resolve through `VidbytePaths`.
6. **Adding a command group** = new folder under `commands/`, one class per command,
   registered in `commands/__init__.py`. Nothing else changes. Add it only once the backend
   route it calls is live; a command that can only report "not implemented" does not ship.
7. **Reusable code does not terminate the process.** `CliApplication.run()` and `cli.main()`
   return an integer. Only generated console wrappers and `__main__.py` raise `SystemExit`.
8. **Process channels are injected.** Runtime and presentation code use `IOStreams`; direct
   writes to `sys.stdout`/`sys.stderr` stay at verification-script or outer process edges.
9. **One invocation owns one dependency graph.** `ApplicationContext` is constructed per
   run and builds every service lazily, so help/version paths stay offline.
10. **Machine output is versioned.** Every JSON/JSONL record carries `schema_version` and
    `kind`. Human prose is not an automation contract.
11. **Stdout is results-only.** Progress, warnings, diagnostics, and errors use stderr. JSON
    emits one final result; only JSONL may stream transition records.
12. **Prompt input is explicit.** One positional value, one UTF-8 file, or the literal `-`
    stdin marker — never a prompt merely because stdin happens to be redirected.
13. **Failures are agent-native.** Every error carries a non-sensitive `description`, `trace`,
    and `file_path`, because agents are this CLI's heaviest callers and have no transcript
    to fall back on.
14. **Secrets have their own precedence.** Credentials resolve environment → scoped OS
    keyring → explicitly approved restricted file. An environment key is never persisted.
15. **Configuration is typed and attributable.** Command → environment → selected profile →
    default profile → built-in, recorded per field so `config get` can report the source.

16. **Local runtime context stays local.** Native agent children inherit the current working
   directory and process environment; environment values and repository contents are never
   serialized into a Vidbyte admission request.

## Local runtime primitives

The `runtime` command family is intentionally independent from hosted research. Host
discovery identifies an installed Codex, Claude Code, or OpenCode executable; launch
planning validates safe local prerequisites; and each primitive decides for itself where
paid admission sits relative to execution.

`same-host-ensemble` is implemented. It lives in `services/ensemble/` rather than in
`RuntimeExecutor`, because a service may depend on `lib/` while nothing in `lib/` may depend on
a service. It runs only on `codex`, the one host with a merged Vidbyte SDK adapter and verified
native fork and sandbox control, and it resolves that SDK before requesting admission so an
unmet local dependency costs the caller nothing.

`adversarial-team` is still a scaffold, and it is now the sole exception to rule 6:
`RuntimeExecutor` always raises before payment or process launch. The exception disappears when
that primitive is built.

## Output and failure contracts

Root presentation flags precede the command:

```text
--format human|json|jsonl|none
--json
--profile NAME
--no-input
--color auto|always|never
--debug
```

`--json` is exactly an alias for `--format json`; pairing it with another format is a usage
error. `none` suppresses results and transitions but never actionable failures. Terminal
control is off when stderr is not a TTY, when `TERM=dumb`, or when `NO_COLOR` is set, even if
color was requested.

Exit statuses are stable:

| Status | Meaning |
| --- | --- |
| `0` | success (including a normal downstream broken pipe) |
| `1` | operational failure |
| `2` | invalid command usage |
| `3` | partial research outcome when `--exit-status` is requested |
| `4` | authentication failure |
| `5` | credit exhaustion |
| `70` | internal software error |
| `130` | user interrupt |

A machine error is a version-1 `kind=error` document on stderr carrying the stable code, exit
status, safe message, `description`, `trace`, `file_path`, retryability, and an optional hint
and request ID. The private `cause` is never serialized.

## The root-option pre-scan

`lib/runtime/options.py` scans argv's root-option prefix once before Click parses anything.
This is not a second parser: Click stays authoritative and renders every syntax error. The
scan exists because `--format` and `--debug` decide *how* a parse failure is rendered, and
Click's own errors leave through the same `ErrorHandler` boundary as everything else. Without
it, `vidbyte-cli --format json --not-an-option` would fail correctly and print human prose to
a caller who asked for JSON.

The scan stops at the first positional token, so no command name or argument value can be
mistaken for a root option, and it touches no service — `--help` and `--version` short-circuit
before configuration is resolved, which is what keeps them off the filesystem.

## Verification boundary

`scripts/run_ci.py` is the one local and remote verification entry point. It runs Ruff,
strict mypy, byte compilation, offline CLI smoke, distribution build, Twine metadata checks,
and an installed-wheel smoke outside the source checkout. `.github/workflows/ci.yml` supplies
the OS/Python matrix and invokes that script without duplicating its steps.

The approved program intentionally adds no feature test files. This makes the smoke and
package gates startup/packaging evidence rather than proof of use-case correctness; the
constraint and residual risk are recorded in
`docs/design/python-cli-research-harness-program.md`.

## Backend contract

The CLI calls seven routes, and only seven. Six are the entire API-key research surface the
backend serves; the seventh proves a key is live.

| Method | Path | Scope | Commands |
| --- | --- | --- | --- |
| `POST` | `/api/skills/auth/validate` | — | `login`, `whoami` |
| `POST` | `/api/v1/research/run` | `research:write` | `research start` |
| `POST` | `/api/v1/research/threads/{encrypted_id}/run` | `research:write` | `research add` |
| `POST` | `/api/v1/research/runs/{run_id}/continue` | `research:write` | `research resume` |
| `GET` | `/api/v1/research/runs/{run_id}` | `research:read` | `research status`, `research watch` |
| `GET` | `/api/v1/research/portfolio` | `research:read` | `research threads` |
| `GET` | `/api/v1/research/threads/{encrypted_id}` | `research:read` | `research thread` |

The three writes are priced and require an `Idempotency-Key`; the three reads are free and
rate-limited. There is no sources, artifacts, capabilities, export, deep-dive, or run-listing
route on the API-key surface, so `lib/api/endpoints/research.py` has no method for one — the
authority is `backend/lib/app/route_rules.py` in the Vidbyte repository.

A thread is addressable **only** by its public share token (`encrypted_id`), which the backend
validates in transport against a UUIDv4 pattern. `types/research.py` binds the CLI's
`thread_id` field to that wire key by alias with `populate_by_name` off, so the backend's
internal identifier is discarded on arrival and can never be printed as something to paste
back. `ResearchRunStatus` declares no thread field at all for the same reason.

Models in `types/api.py` and `types/research.py` mirror the backend DTOs. The system design
for the harness runtime that once lived here is preserved as history in
[docs/design/harness-runtime-and-cli-scaffold.md](design/harness-runtime-and-cli-scaffold.md);
it describes routes the backend never shipped and is not a live contract. Why that surface was
removed is recorded in
[docs/design/research-only-command-surface.md](design/research-only-command-surface.md).
