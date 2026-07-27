# `src/vidbyte_cli/lib`

Reusable client-platform mechanisms shared by command groups and future feature slices:
transport, credentials, configuration, output, process runtime, repository inspection, and
generic harness mechanics. Everything here stays independent of any one product capability.

**Blast radius:** most of the installed CLI depends on this layer, so a changed public
contract can affect registration, auth, network behavior, persistence, and every harness.

## Non-goals

- No top-level click commands (`commands/`) and no hand-written harness policy
  (`harnesses/`).
- No product domain models — `types/` owns shared wire shapes; feature slices own their own.
- No module-global service instances; `lib/runtime` owns invocation composition.
- No secret reads outside `lib/auth`, and never in errors or rendered output.

## Files

- `__init__.py` — package marker only. Prefer each subpackage's own facade so ownership and
  optional dependencies stay explicit.

## Log

- 2026-07-26 — Kept the platform layer product-neutral so research and future harnesses can
  share mechanisms without sharing domain policy.
