# `src/vidbyte_cli/lib/harness`

The generic mechanism that turns a typed harness command description into a click subtree
and a backend invocation lifecycle. Manifest-driven harnesses and hand-written enrichments
satisfy one contract and share the same guard, translation, submission, waiting,
presentation, and error-mapping boundaries — so adding a harness never touches the CLI
bootstrap.

**Blast radius:** used whenever argv names a harness namespace, so changes affect every
harness command, request envelope, help tree, polling behavior, and backend error mapping.

## Non-goals

- No single harness's product policy (`harnesses/`) and no direct HTTPX calls (`lib/api`).
- No credential persistence (`lib/auth`) and no `sys.exit` (`lib/runtime`).
- Never load every manifest at startup; the runtime attaches only the requested namespace.
- Never execute backend-supplied content — manifests are data.

## Files

- `base.py` — `BaseHarness`: shared click registration and the submit → (await) → present →
  map-errors lifecycle. Add here only when a concern is identical for all harnesses.
- `types.py` — command-as-data definitions plus optional translation/presentation hooks.
- `module.py` — the protocol both static and manifest-backed harness modules satisfy.
- `manifest_harness.py` — adapts a validated manifest to `BaseHarness` with no custom code.
- `catalog.py` — cache-first manifest loading and `min_cli_version` enforcement.
- `registry.py` — resolves a namespace and attaches exactly one subtree; static enrichments
  intentionally win over manifest-generated modules.
- `context.py` — the services available to generic harness execution.
- `invocation.py` — parsed params + optional repo facts → the shared request envelope.
- `errors.py` — maps backend failures to safe `CliError`s; never leaks secrets.

## Log

- 2026-07-26 — Kept one contract for static and manifest harnesses, so registration and
  dispatch downstream are identical regardless of how a namespace was discovered.
- 2026-07-26 — Dropped the generic parameter on `click.ParamType`, which is not present in
  the supported click 8.1 baseline, to keep strict typing green across the version range.
