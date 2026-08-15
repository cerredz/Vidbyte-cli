# `src/vidbyte_cli/lib/runtime`

Owns the lifecycle of one synchronous CLI invocation: composition, dependency scope, version
discovery, command-tree construction, dispatch, and return-code mapping. This exists so the
console entry point stays a tiny adapter and reusable code never terminates a caller's
process.

**Blast radius:** both the console script and `python -m` flow through here, so changes
affect every command, global option, exit status, and startup cost.

## Non-goals

- No command use cases, formatting (`lib/output`), transport (`lib/api`), credentials
  (`lib/auth`), or config precedence (`lib/config`).
- No `sys.exit` — `cli.py` and `__main__.py` own process termination.
- No optional service construction at import time; `ApplicationContext` owns that, lazily.

## Files

- `__init__.py` — re-exports only version contracts that are safe during `import
  vidbyte_cli`. Keep application and command dependencies out.
- `application.py` — `CliApplication`: builds the tree, dispatches click, and sends every
  failure to the one `ErrorHandler`.
- `context.py` — `ApplicationContext`: invocation-scoped services and resolved root policy,
  created lazily. Never let it become a process-global service locator.
- `options.py` — `RootOptionInspector`: a service-free read of the root-option prefix, run
  before click parses so `--format` governs how a *parse failure* is rendered.
- `version.py` — resolves the installed distribution version, with a source-tree fallback.
  Release numbers stay owned by `pyproject.toml`.

## Log

- 2026-07-26 — Moved process exit out of reusable runtime code; embedding callers now get an
  integer status.
- 2026-07-26 — Preserved lazy one-harness attachment so unrelated commands stay network-free.
- 2026-07-26 — Read root options before attachment, so `--profile harness` and invalid root
  syntax can no longer trigger dynamic harness construction.
- 2026-08-15 — Deleted harness attachment with the harness runtime. `RootOptionInspector`
  stayed: its second job — settling output policy before click can raise a syntax error
  through `ErrorHandler` — is what keeps `--format json --not-an-option` a machine document.
