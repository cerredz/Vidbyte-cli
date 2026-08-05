# `src/vidbyte_cli/lib/runtime`

## Folder Description / Intent

This folder owns the lifecycle of one synchronous CLI invocation: composition, dependency
scope, version discovery, command-tree construction, dispatch, and return-code mapping. It
exists so the console entry point stays a tiny adapter and so an embedding caller can run
the same CLI without allowing reusable code to terminate its process. The design optimizes
for deterministic startup and lazy construction of stateful services.

This folder is not for command business logic, presentation formatting, or HTTP behavior.
Commands and feature slices own use cases, `lib/output` owns formatting, and `lib/api` owns
transport.

## Blast Radius

The installed console script and module entry point both flow through this folder. Changes
can affect every command, global option, dynamic harness attachment, exit status, and
startup-time side effect.

## Non-Goals

- Do not implement command use cases; `src/vidbyte_cli/commands` and feature slices own them.
- Do not format result documents; `src/vidbyte_cli/lib/output` owns presentation.
- Do not perform HTTP requests; `src/vidbyte_cli/lib/api` owns transport.
- Do not persist credentials; `src/vidbyte_cli/lib/auth` owns secret storage.
- Do not resolve profile precedence; `src/vidbyte_cli/lib/config` owns configuration.
- Do not define research states; `src/vidbyte_cli/features/research/domain` owns them.
- Do not call `sys.exit`; `src/vidbyte_cli/cli.py` and `__main__.py` own process termination.
- Do not instantiate optional services at import time; the invocation context owns them.

## File Index

- `__init__.py` - Re-exports only version contracts that are safe during top-level package
  import. Open this when a lightweight runtime contract becomes broadly useful. Keep
  application and command dependencies out so `import vidbyte_cli` stays cheap.
- `application.py` - Coordinates command-tree creation, lazy harness attachment, Click
  dispatch, and centralized return-code mapping. Open this for global lifecycle or error
  boundary changes. Command-specific behavior must remain outside the composition root.
- `context.py` - Lazily creates config, credential, pooled API, and harness services only
  when required. It also binds root options, output, and the error handler.
- `clock.py` - Injectable monotonic clock and cancellation-aware sleeping for polling.
- `signals.py` - Cooperative SIGINT/SIGTERM scope; never implies remote cancellation.
- `options.py` - Performs the service-free root-option scan needed before dynamic harness
  attachment and reconstructs Click callback values. Open whenever a root flag changes so
  the preflight parser cannot drift from the public command.
- `version.py` - Resolves the installed distribution version with a source-tree fallback.
  Open this for package-renaming or metadata-resolution behavior. Normal release numbers
  remain owned by `pyproject.toml`.

## Logs

- 2026-07-26 - Moved process exit out of reusable runtime code - embedding callers now receive an integer status.
- 2026-07-26 - Preserved lazy one-harness attachment - unrelated help and platform commands remain network-free.
- 2026-07-26 - Bound root output and interaction flags per invocation - help stays offline while command output shares one policy.
- 2026-07-26 - Delegated every boundary failure to ErrorHandler - safe messages and exit statuses no longer diverge by command.
- 2026-07-26 - Split root preflight parsing from application dispatch - option values cannot masquerade as harness namespaces.
- 2026-07-26 - Added deterministic client cleanup and cooperative cancellation - remote work remains recoverable after local interruption.
