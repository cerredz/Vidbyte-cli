# `src/vidbyte_cli/commands`

## Folder Description / Intent

This folder owns Click adapters for stable, cross-product command namespaces known at CLI
release time. It exists to translate terminal arguments into calls on reusable platform
services while keeping parsing separate from behavior. The boundary optimizes for a command
tree that can be built synchronously without credentials, repository inspection, or network
access.

This folder is not for dynamic per-harness manifests, reusable transport/configuration
mechanisms, or research domain behavior. Generic harness mechanics belong in
`src/vidbyte_cli/lib/harness`, platform services belong in `src/vidbyte_cli/lib`, and
product-specific commands belong in their feature slice.

## Blast Radius

`lib/runtime/application.py` calls this folder's registration facade for every invocation,
including help and version. Changes affect root help, command discovery, parsing, and which
feature boundaries become reachable.

## Non-Goals

- Do not make HTTP calls during registration; `src/vidbyte_cli/lib/api` owns transport.
- Do not access credentials during registration; `src/vidbyte_cli/lib/auth` owns secrets.
- Do not inspect repositories during registration; `src/vidbyte_cli/lib/git` owns inspection.
- Do not render result schemas inline; `src/vidbyte_cli/lib/output` owns shared presentation.
- Do not attach dynamic harness manifests; `src/vidbyte_cli/lib/runtime` owns the second pass.
- Do not define research domain policy here; `src/vidbyte_cli/features/research` owns it.
- Do not call `sys.exit`; `src/vidbyte_cli/lib/runtime` owns status mapping.
- Do not build process-global services; `ApplicationContext` owns invocation dependencies.

## File Index

- `__init__.py` - Registers stable root and subgroup adapters, then returns the generic
  harness group used by dynamic attachment. Open this when adding a cross-product command
  namespace or attaching a first-class feature registration function. Keep construction
  side-effect free because every help path executes it.

## Logs

- 2026-07-26 - Split group registration into small routing helpers - keeps the static command tree readable without moving behavior into the facade.
