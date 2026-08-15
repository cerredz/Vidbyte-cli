# `src/vidbyte_cli`

The installable Python package. It owns the executable bootstrap and the package's public
surface, and delegates everything else — commands, platform mechanisms, wire types — to
narrower packages. Importing it must stay cheap and side-effect free.

**Blast radius:** loaded by the `vidbyte-cli` console script and `python -m vidbyte_cli`, so
its direct files affect every invocation and the packaging smoke checks.

## Non-goals

- No HTTP (`lib/api`), credentials (`lib/auth`), config (`lib/config`), or formatting
  (`lib/output`) here.
- No command definitions (`commands/`) or reusable mechanisms (`lib/`) here.

## Files

- `__init__.py` — publishes `__version__` from installed distribution metadata. Keep it free
  of import side effects; every consumer loads it first.
- `__main__.py` — turns the status returned by `cli.main()` into `SystemExit` for
  `python -m vidbyte_cli`. Nothing else belongs here.
- `cli.py` — the console-script callable; delegates to `lib/runtime`. Lifecycle decisions
  belong in the application object, not this shim.

## Log

- 2026-07-26 — Made the top-level package a thin executable boundary, keeping imports cheap
  and lifecycle policy centralized in `lib/runtime`.
