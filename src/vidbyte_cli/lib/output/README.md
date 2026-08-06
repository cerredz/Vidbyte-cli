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
- `logger.py` — the generic harness runtime's info/warn/error, adapted onto OutputManager.
  A compatibility shim; new code uses OutputManager directly.
- `render.py` — human presenter for generic harness runs.

## Log

- 2026-07-26 — Made output policy invocation-owned; root flags configure one shared manager
  instead of process-global streams.
- 2026-07-26 — Versioned machine documents at schema 1, so consumers can branch on `kind`.
- 2026-07-26 — Reserved stdout for results; everything else is shell-safe on stderr.
