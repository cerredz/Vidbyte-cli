# `src/vidbyte_cli/lib/output`

## Folder Description / Intent

This folder owns presentation contracts shared by every CLI feature: output and color
preferences, versioned machine documents, stdout/stderr policy, and the temporary generic
harness logger adapter. It exists so commands describe results while one invocation-owned
manager decides how and where those results are emitted.

This folder is not for physical terminal discovery, exception classification, or
feature-specific prose. `lib/io` owns streams and capabilities, `lib/errors` owns failure
identity, and feature presenters own their human and machine data.

## Blast Radius

Changes can affect shell pipelines, automation schemas, error readability, progress
visibility, and stdout cardinality for every command. Treat `schema_version`, `kind`, and
document data keys as public compatibility contracts.

## Non-Goals

- Do not call process-global `print`, `sys.stdout`, or `sys.stderr`.
- Do not place progress, warnings, diagnostics, or errors on stdout.
- Do not serialize exception causes, API keys, full prompts, or backend response bodies.
- Do not silently fall back from machine output to human output.
- Do not add research-specific artifact or source formatting here.
- Do not instantiate a module-global output manager or logger.
- Do not generate ANSI escapes without capabilities from `lib/io`.
- Do not treat human text as an automation contract.

## File Index

- `__init__.py` - Public output facade. Open when a platform-wide output contract becomes a
  cross-package dependency; keep feature presenters private to their slices.
- `formats.py` - Root output and color enums. Open when changing public flag vocabulary and
  update every manager branch plus architecture docs in the same change.
- `models.py` - Versioned machine-document envelope and safe error conversion. Open when
  evolving JSON compatibility; never remove `schema_version` or `kind`.
- `manager.py` - OutputPolicy plus human/machine selection and stdout/stderr enforcement.
  Open for shell behavior or serialization policy, not command-specific formatting.
- `logger.py` - Legacy generic harness adapter over OutputManager. Open only while
  modernizing generic harness presentation; new feature code uses OutputManager directly.
- `render.py` - Existing human harness run renderer seam. Open for generic harness display;
  research-specific presenters belong under the research feature.

## Logs

- 2026-07-26 - Made output policy invocation-owned - root flags now control one shared manager without process-global streams.
- 2026-07-26 - Versioned machine documents at schema 1 - JSON and JSONL consumers can branch on stable kind values.
- 2026-07-26 - Reserved stdout for result records - progress, warnings, diagnostics, and errors remain shell-safe on stderr.
