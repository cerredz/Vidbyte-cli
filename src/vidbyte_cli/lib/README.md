# `src/vidbyte_cli/lib`

## Folder Description / Intent

This folder contains reusable client-platform mechanisms shared by command groups and
feature slices. It exists to keep transport, credentials, configuration, output, process
runtime, repository inspection, and generic harness mechanics independent of any one
product capability. The boundary optimizes for explicit dependency direction and reuse by
future harnesses.

This folder is not for Click command declarations or research-specific product policy.
Command adapters belong in `src/vidbyte_cli/commands`; product vertical slices belong in
`src/vidbyte_cli/features`; hand-authored harness enrichments belong in
`src/vidbyte_cli/harnesses`.

## Blast Radius

Modules throughout the installed CLI depend on this platform layer. A changed public
contract can affect command registration, authentication, network behavior, persistence,
rendering, and every harness feature, so additions should remain narrow and typed.

## Non-Goals

- Do not declare top-level Click commands here; `src/vidbyte_cli/commands` owns them.
- Do not encode research states or exports here; `src/vidbyte_cli/features/research` owns them.
- Do not register hand-written harnesses here; `src/vidbyte_cli/harnesses` owns policy.
- Do not mirror backend DTOs opportunistically here; `src/vidbyte_cli/types` owns shared wire shapes.
- Do not run backend harness logic locally; the Vidbyte API owns execution.
- Do not introduce module-global service instances; `lib/runtime` owns invocation composition.
- Do not write directly to process streams outside the I/O and output boundaries.
- Do not read secrets outside `lib/auth` or include them in errors and rendered output.

## File Index

- `__init__.py` - Marks the reusable platform package without creating a broad convenience
  export surface. Open it only when a genuinely package-wide contract needs a stable import.
  Prefer each focused subpackage facade so optional dependencies and ownership stay clear.

## Logs

- 2026-07-26 - Kept the platform package product-neutral - lets research and future harnesses share mechanisms without sharing domain policy.
