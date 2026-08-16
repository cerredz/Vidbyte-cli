# `src/vidbyte_cli/commands`

Click adapters for every command namespace, all of them known at CLI release time. They
translate terminal arguments into calls on reusable platform services, keeping parsing
separate from behavior. The whole tree must build synchronously with no credentials or
network access.

**Blast radius:** `lib/runtime/application.py` calls this folder's registration facade on
every invocation, including `--help` and `--version`.

## Non-goals

- No HTTP or credential access during registration.
- No dynamic or manifest-driven commands. The surface is entirely static, so `__init__.py`
  is the complete list of what `--help` can show.
- No command whose backend route is not live. A command that parses and then reports "not
  implemented" is worse than an absent one — it teaches a user the CLI is broken.
- No `sys.exit` and no process-global services; `ApplicationContext` owns dependencies.

## Files

- `__init__.py` — registers every group. Keep it side-effect free: every help path executes
  it.

## Log

- 2026-07-26 — Documented that registration stays side-effect free, which is what keeps
  `--help` and `--version` offline.
- 2026-08-15 — Removed the harness group and `connect github`, whose backend routes were
  never built, and with them the static/dynamic seam. Registration returns nothing now.
