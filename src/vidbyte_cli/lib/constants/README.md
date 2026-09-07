# Runtime constants

Shared runtime policy and presentation values live here so commands and execution
use the same vocabulary. Receipt models belong in `types/`; admission checks and
agent orchestration belong in `lib/runtime_primitives/`.

## File index

- `__init__.py` marks the package without eagerly importing execution dependencies.
- `runtime.py` defines admission reasons, execution limits, Codex configuration,
  and user-facing progress messages. Read it when changing runtime policy or wording.

## Non-goals

Do not resolve credentials, perform HTTP requests, launch agents, or load prompts
here. These are values, not services.

## Logs

- 2026-09-07 - Centralized runtime enums after PR #26 review to prevent scattered literals.
