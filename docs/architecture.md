# Vidbyte CLI Architecture

This document records the layering rules that keep the CLI scalable as command surfaces
grow (billing, skills, MCP, and future harnesses all land as additive modules).

## The layers

```text
bin/vidbyte.js          executable shim → dist/index.js
src/index.ts            program bootstrap + central error trap (owns process.exit)
src/commands/<group>/   one class per command: register() + private execute()
src/lib/api/client.ts   ApiClient: base URL, API-key header, envelope unwrapping
src/lib/api/endpoints/  typed endpoint groups (harness, auth, ...) built on ApiClient
src/lib/auth/           CredentialStore (~/.vidbyte/credentials.json)
src/lib/config/         ConfigStore + VidbytePaths (single source of ~/.vidbyte paths)
src/lib/git/            RepoInspector: origin URL, HEAD sha, branch, dirty state
src/lib/output/         Logger + renderers (the only modules that format terminal output)
src/lib/errors/         CliError with exit codes
src/types/              API types mirroring backend DTOs (backend/lib/dtos/harness.py)
```

## Rules

1. **Commands are thin.** A command class parses arguments, calls lib services, and hands
   results to a renderer. Commands never call `fetch`, touch the filesystem stores, or
   call `process.exit` directly.
2. **All HTTP goes through `ApiClient`** via a typed endpoint group. New backend surfaces
   get a new file in `src/lib/api/endpoints/`, never inline requests.
3. **Errors are thrown, not printed.** Anything user-facing throws `CliError(message,
   exitCode)`; the trap in `src/index.ts` renders it and exits. Unexpected errors exit 70.
4. **Secrets never log.** The API key may not appear in log lines, error messages, or
   rendered output.
5. **Paths have one source of truth.** Anything under `~/.vidbyte` resolves through
   `VidbytePaths`.
6. **Adding a command group** = new folder under `src/commands/`, one class per command,
   registered in `src/commands/index.ts`. Nothing else changes.

## Backend contract

The CLI targets the Vidbyte public API-key surface (`Authorization` via Vidbyte API key):

- `POST /harness/run` — submit a run (`{harness, task, repo:{url, sha, branch}}`)
- `GET /harness/get/{run_id}` — status, events, result
- `GET /harness/list` — the caller's runs

Types in `src/types/api.ts` mirror the backend DTOs; keep them in sync when the backend
routes ship. The full system design (backend runtime + this CLI) lives in
[docs/design/harness-runtime-and-cli-scaffold.md](design/harness-runtime-and-cli-scaffold.md).
