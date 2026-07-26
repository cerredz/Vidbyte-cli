# `src/vidbyte_cli`

## Folder Description / Intent

This folder is the installable Python package for the Vidbyte command-line client. It owns
the executable bootstrap and top-level package contract while delegating all command,
platform, harness, feature, and wire behavior to narrower packages. The boundary optimizes
for a fast, side-effect-free import and one obvious route from the console entry point into
an invocation-owned application.

This folder is not a home for HTTP calls, credential persistence, output formatting, or
research use cases. Reusable client capabilities belong in `src/vidbyte_cli/lib`, static
command adapters belong in `src/vidbyte_cli/commands`, and product-specific vertical slices
belong in `src/vidbyte_cli/features`.

## Blast Radius

This package is imported by the installed `vidbyte-cli` console script and by
`python -m vidbyte_cli`. Changes to its direct files affect every invocation, packaging
metadata smoke checks, and all downstream command groups.

## Non-Goals

- Do not implement HTTP transport here; `src/vidbyte_cli/lib/api` owns remote calls.
- Do not persist API keys here; `src/vidbyte_cli/lib/auth` owns credential storage.
- Do not resolve configuration here; `src/vidbyte_cli/lib/config` owns precedence.
- Do not render human or machine results here; `src/vidbyte_cli/lib/output` owns formatting.
- Do not define static command groups here; `src/vidbyte_cli/commands` owns adapters.
- Do not define harness policy here; `src/vidbyte_cli/harnesses` owns enrichments.
- Do not add reusable mechanisms here; `src/vidbyte_cli/lib` owns platform capabilities.
- Do not add product domain models here; `src/vidbyte_cli/features` owns vertical slices.

## File Index

- `__init__.py` - Publishes the package version obtained from installed distribution
  metadata. Open this when changing the package's intentionally tiny public surface.
  Keep it import-side-effect free because every consumer loads it first.
- `__main__.py` - Converts the integer returned by the reusable CLI entry function into
  `SystemExit` for `python -m vidbyte_cli`. Open this only when changing the process boundary.
  It must not duplicate error handling or command registration.
- `cli.py` - Provides the console-script callable and delegates invocation behavior to
  `lib/runtime`. Open this when changing how embedding callers pass argv or receive a status.
  Runtime lifecycle decisions belong in the application object, not this shim.

## Logs

- 2026-07-26 - Made the top-level package a thin executable boundary - keeps imports cheap and lifecycle policy centralized.
