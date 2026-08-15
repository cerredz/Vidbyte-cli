# `src/vidbyte_cli/lib/output`

Owns what a command's results look like and which stream they leave on. Commands describe
results; one invocation-owned manager decides how they are emitted.

**Blast radius:** shell pipelines and automation schemas. `schema_version`, `kind`, and the
keys inside `data` are public compatibility contracts.

## Non-goals

- No `print`, `sys.stdout`, or `sys.stderr` — `lib/io` owns the physical channels.
- No progress, warnings, diagnostics, or errors on stdout.
- No serialized exception causes, API keys, prompts, or backend response bodies.
- No silent fallback from a machine format to human text.
- No terminal detection (`lib/io`) or exception classification (`lib/errors`).

## Files

- `formats.py` — `OutputFormat` and `ColorMode`, the root presentation vocabulary.
- `models.py` — `OutputDocument`, the versioned envelope, and `from_error` for failures.
- `manager.py` — `OutputManager`: format selection and the stdout/stderr contract.

Human presentation for a product's own result shapes lives beside that product — see
`commands/research/render.py`, which emits both encodings together so they cannot drift.

## Log

- 2026-07-26 — Made output policy invocation-owned; root flags configure one shared manager
  instead of process-global streams.
- 2026-07-26 — Versioned machine documents at schema 1, so consumers can branch on `kind`.
- 2026-07-26 — Reserved stdout for results; everything else is shell-safe on stderr.
- 2026-08-15 — Removed `logger.py` and `render.py` with the harness runtime they served.
  `OutputManager` is now the only writer, which is what the logger shim was deferring.
