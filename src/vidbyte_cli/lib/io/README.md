# `src/vidbyte_cli/lib/io`

## Folder Description / Intent

This folder owns process-I/O abstractions used by one CLI invocation. It exists to separate
the physical stdin/stdout/stderr channels from presentation policy so commands can be
embedded, redirected, and exercised without monkey-patching `sys`. The boundary optimizes
for explicit stream ownership and shell-safe stdout/stderr behavior.

This folder is not for choosing JSON schemas, color policy, progress rendering, or command
results. Those responsibilities belong in `src/vidbyte_cli/lib/output`; prompt-source
selection may live here only when it is generic process input rather than product policy.

## Blast Radius

The runtime application and output layer depend on these channels. Changes can affect shell
pipelines, captured output, interactive prompting, Windows console behavior, and every
error path.

## Non-Goals

- Do not define output document schemas; `src/vidbyte_cli/lib/output` owns them.
- Do not choose human versus JSON mode; the invocation output policy owns that decision.
- Do not format research artifacts; the research presentation slice owns that behavior.
- Do not read API keys from stdin; `src/vidbyte_cli/lib/auth` owns credential input policy.
- Do not call `sys.exit`; `src/vidbyte_cli/lib/runtime` owns return-code mapping.
- Do not close caller-provided streams; the embedding process owns their lifecycle.
- Do not assume every stream is a TTY; redirected and in-memory streams are supported.
- Do not write command results from arbitrary services; route them through output policy.

## File Index

- `__init__.py` - Re-exports the public I/O contracts used by runtime composition. Open this
  when a new generic channel or capability becomes a stable cross-package dependency.
  Keep optional terminal dependencies out of this always-loaded facade.
- `streams.py` - Defines the immutable stdin/stdout/stderr bundle and small write methods.
  Open this when changing physical stream injection or flush behavior. Formatting, color,
  and machine-document decisions do not belong in this file.

## Logs

- 2026-07-26 - Bound streams per invocation instead of at module import - preserves redirection and embedding behavior.
