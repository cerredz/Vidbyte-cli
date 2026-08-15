# `src/vidbyte_cli/lib`

Reusable client-platform mechanisms shared by command groups and future feature slices:
transport, credentials, configuration, output, and process runtime. Everything here stays
independent of any one product capability.

**Blast radius:** most of the installed CLI depends on this layer, so a changed public
contract can affect registration, auth, network behavior, and persistence.

## Non-goals

- No top-level click commands (`commands/`).
- No product domain models — `types/` owns shared wire shapes; feature slices own their own.
- No module-global service instances; `lib/runtime` owns invocation composition.
- No secret reads outside `lib/auth`, and never in errors or rendered output.

## Files

- `__init__.py` — package marker only. Prefer each subpackage's own facade so ownership and
  optional dependencies stay explicit.

## Log

- 2026-07-26 — Kept the platform layer product-neutral so research and future harnesses can
  share mechanisms without sharing domain policy.
- 2026-08-15 — Removed `lib/harness` and `lib/git`; both existed only for backend routes that
  were never built. The layer stays product-neutral, with one product on it.
