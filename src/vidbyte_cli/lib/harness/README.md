# `src/vidbyte_cli/lib/harness`

## Folder Description / Intent

This folder owns the generic mechanism that turns a typed harness command description into
a Click subtree and a backend invocation lifecycle. It exists so backend-manifest harnesses
and optional hand-written enrichments satisfy one contract and reuse the same guard,
translation, submission, waiting, presentation, and error-mapping boundaries. The design
optimizes for adding harnesses without changing the CLI bootstrap.

This folder is not for a specific harness's product policy, direct HTTPX calls, credential
persistence, or research-specific state. Hand-written harness policy belongs in
`src/vidbyte_cli/harnesses`, product slices belong in `src/vidbyte_cli/features`, and HTTP
transport belongs in `src/vidbyte_cli/lib/api`.

## Blast Radius

The runtime composition root uses this folder whenever argv selects a harness namespace.
Changes can affect all manifest-driven and hand-written harness commands, request envelopes,
help-tree construction, polling behavior, and backend error mapping.

## Non-Goals

- Do not encode one harness's product policy; `src/vidbyte_cli/harnesses` owns enrichments.
- Do not define research threads or artifacts; `src/vidbyte_cli/features/research` owns them.
- Do not make direct HTTPX calls; `src/vidbyte_cli/lib/api` owns transport.
- Do not persist API keys; `src/vidbyte_cli/lib/auth` owns credential storage.
- Do not render arbitrary command output in Click callbacks; output collaborators own it.
- Do not load every manifest at startup; runtime attaches only the requested namespace.
- Do not run harness execution locally; the Vidbyte backend owns execution.
- Do not call `sys.exit`; the invocation runtime owns return-code mapping.

## File Index

- `__init__.py` - Re-exports the stable generic harness contracts used outside this folder.
  Open it when an existing implementation type becomes a supported cross-package import.
  Keep exports narrow to preserve implementation freedom.
- `base.py` - Implements the common Click registration and backend dispatch lifecycle for
  every harness definition. Open it when a concern is identical across all harnesses.
  Harness-specific options and presentation hooks belong in policy modules instead.
- `catalog.py` - Defines cache-first manifest loading and refresh boundaries, currently
  scaffolded until the HTTP platform PR. Open it for manifest retrieval, cache, or
  compatibility policy. It must not construct command trees.
- `context.py` - Defines services available to generic harness execution and creates the
  current endpoint group. Open it when every harness needs a new reusable collaborator.
  Avoid adding feature-specific services to this shared context.
- `errors.py` - Maps backend and validation failures into safe CLI-facing errors. Open it
  when the generic harness envelope gains a failure shape. It must never expose secrets or
  internal server diagnostics.
- `invocation.py` - Translates parsed command parameters and optional repository facts into
  the shared backend request envelope. Open it when generic request semantics change.
  Per-harness translation remains an explicit hook rather than a branch here.
- `manifest_harness.py` - Adapts a validated backend manifest to BaseHarness without custom
  policy code. Open it when manifest schema capabilities expand. Never execute provider or
  backend-supplied code.
- `module.py` - Declares the protocol satisfied by static and manifest-backed harness
  modules. Open it before changing the cross-source harness contract. Keep it structural
  and free of construction side effects.
- `registry.py` - Resolves a namespace from the static enrichment map or manifest catalog
  and attaches exactly one subtree. Open it for resolution precedence or attachment policy.
  Static enrichments intentionally win over manifest-generated modules.
- `types.py` - Defines command-as-data contracts and optional translation/presentation
  hooks. Open it when the reusable command description needs a typed capability. Avoid
  embedding Click objects or transport clients into these definitions.

## Logs

- 2026-07-26 - Preserved one contract for static and manifest harnesses - keeps downstream registration and dispatch identical.
- 2026-07-26 - Removed an obsolete generic parameter from Click ParamType - keeps strict typing compatible with supported Click releases.
