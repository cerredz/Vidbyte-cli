# `src/vidbyte_cli/lib/errors`

## Folder Description / Intent

This folder owns platform-wide failure identity, safe exception data, process statuses, and
the single application-boundary exception mapper. It exists so commands and services raise
classified failures without printing, leaking internals, or terminating the embedding
process.

This folder is not for feature-domain failures or backend-provider details. Feature
adapters map their own failures into `CliError`; transport decoding belongs in `lib/api`.

## Blast Radius

Changes can affect every failed invocation, shell branching, automation error handling,
debug disclosure, and support diagnostics. Existing error-code strings and exit numbers are
public contracts and must remain stable.

## Non-Goals

- Do not stringify unexpected exceptions into user-facing messages.
- Do not include credentials, full prompts, authorization headers, or response bodies.
- Do not render or terminate from command and service code.
- Do not allocate feature-specific exit codes when a base category is sufficient.
- Do not expose cause in human or machine error documents.
- Do not include exception values or locals in debug traces.
- Do not call `sys.exit`; runtime returns integer statuses.
- Do not make backend prose the stable machine identity.

## File Index

- `__init__.py` - Public typed-error facade. Open when exporting a platform-wide error
  contract; do not import feature packages.
- `codes.py` - Stable machine codes and shell exit numbers. Open only for a genuinely new
  recovery branch and never renumber existing statuses.
- `cli_error.py` - Display-safe exception and common constructors. Open when adding safe
  metadata; causes remain private.
- `handler.py` - Click/interrupt/broken-pipe/unexpected exception boundary. Open for
  platform-wide mapping; feature-specific mapping stays with its adapter.

## Logs

- 2026-07-26 - Introduced stable error codes alongside coarse exit statuses - automation no longer parses prose.
- 2026-07-26 - Redacted unexpected failures by default - exception values remain private even in debug frame traces.
- 2026-07-26 - Normalized Ctrl-C to 130 and broken pipes to success - shell behavior now follows explicit contracts.
