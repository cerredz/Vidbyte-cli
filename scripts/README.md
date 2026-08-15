# `scripts`

Repository verification entry points, run directly by developers and by GitHub Actions. One
canonical local command performs exactly the same checks as remote CI.

**Blast radius:** `run_ci.py` is the merge gate for all seven stacked PRs, and
`.github/workflows/ci.yml` invokes it on every supported platform. Steps must be
deterministic and runnable from the repository root on Windows, macOS, and Linux.

## Non-goals

- No production CLI behavior — `src/vidbyte_cli` owns the installed package.
- No publishing or deployment; this repository is a client package.
- No live credentials or network calls, and no mutation of user config/credential stores.
- No duplicated step lists in workflow YAML — `run_ci.py` is the one sequence.
- No feature test packs (excluded by the approved `design-doc-no-tests` workflow).

## Files

- `run_ci.py` — lint, format, strict typing, byte compilation, offline smoke, build, Twine
  metadata, and clean-wheel install. Open when changing the repository-wide gate.
- `smoke.py` — boots the package through its public module entry point and renders
  representative help screens. Open when the public command tree changes.
- `test_login_key_verification.py` — drives the real `ApiClient` against a loopback server to
  prove login verifies before it persists. Open when auth or transport changes.
- `test_research_only_surface.py` — proves the command tree is exactly the set the shipped API
  can answer, and that nothing deleted is still importable or still named in authored prose.
  Open when adding or removing a command.

## Log

- 2026-07-26 — Centralized local and remote verification in `run_ci.py`, so developer and
  workflow checks cannot drift.
- 2026-08-15 — Added a surface gate. A command whose backend route does not exist is a defect
  this repository can now fail on, rather than one a user discovers by running it.
