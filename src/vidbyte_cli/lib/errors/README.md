# `src/vidbyte_cli/lib/errors`

Owns failure identity, the display-safe exception, and the one place an exception becomes a
process status. It exists so commands and services raise classified failures instead of
printing them or terminating a caller's process.

**Blast radius:** every failed invocation. Error-code strings and exit numbers are published
contracts — a shipped value may not be reworded or renumbered.

## Non-goals

- No feature-domain failures. A feature adapter maps its own failures into a `CliError`.
- No stringified foreign exceptions in user output; a backend exception may quote a
  credential, a prompt, or a response body.
- No `cause` in human or machine output, and no locals or exception values in debug traces.
- No `sys.exit` — `lib/runtime` returns integer statuses.

## Files

- `codes.py` — `CliErrorCode` and `ExitCode`, the stable vocabulary. Open only for a genuinely
  new recovery branch.
- `cli_error.py` — `CliError`: the safe message plus the agent-native
  `description`/`trace`/`file_path` triple, and the private `cause`.
- `failures.py` — one subclass per failure the platform raises, carrying its own prose so a
  raise site is one line. New failures go here.
- `handler.py` — the single boundary: one match statement over everything that can reach
  `CliApplication.run`.

## Log

- 2026-07-26 — Split stable codes from prose, so automation branches on identity while
  messages keep improving.
- 2026-07-26 — Gave every failure agent-native description/trace/file_path, since the CLI's
  heaviest callers are agents that must repair their own invocation.
- 2026-07-26 — Normalized Ctrl-C to 130 and a broken stdout pipe to success.
