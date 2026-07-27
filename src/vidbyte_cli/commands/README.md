# `src/vidbyte_cli/commands`

Click adapters for the stable command namespaces known at CLI release time. They translate
terminal arguments into calls on reusable platform services, keeping parsing separate from
behavior. The whole tree must build synchronously with no credentials, repository
inspection, or network access.

**Blast radius:** `lib/runtime/application.py` calls this folder's registration facade on
every invocation, including `--help` and `--version`.

## Non-goals

- No HTTP, credential, or repository access during registration.
- No dynamic harness manifests — `lib/runtime` owns the second pass; `lib/harness` owns the
  generic mechanism.
- No `sys.exit` and no process-global services; `ApplicationContext` owns dependencies.

## Files

- `__init__.py` — registers the stable groups and returns the generic `harness` group for
  dynamic attachment. Keep it side-effect free: every help path executes it.

## Log

- 2026-07-26 — Documented that registration stays side-effect free, which is what keeps
  `--help` and `--version` offline.
