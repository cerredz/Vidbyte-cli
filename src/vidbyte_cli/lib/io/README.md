# `src/vidbyte_cli/lib/io`

Owns the physical process channels one invocation reads and writes, separated from
presentation policy. Commands can then be embedded, redirected, and captured without
monkey-patching `sys`.

**Blast radius:** the runtime and output layers depend on these channels, so changes affect
shell pipelines, captured output, prompting, Windows console behavior, and every error path.

## Non-goals

- No output schemas, human-vs-JSON mode, or color policy — `lib/output` owns those.
- No credential input; `lib/auth` owns that policy.
- No `sys.exit`; `lib/runtime` owns return-code mapping.
- Never close caller-provided streams, and never assume a stream is a TTY.

## Files

- `__init__.py` — the public I/O facade. Keep optional terminal dependencies out of it, since
  it is always loaded.
- `streams.py` — `IOStreams`, the immutable stdin/stdout/stderr bundle and its write helpers.

## Log

- 2026-07-26 — Bound streams per invocation rather than at module import, preserving
  redirection and embedding behavior.
