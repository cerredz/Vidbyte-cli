# `scripts`

## Folder Description / Intent

This folder contains repository verification entry points that developers and GitHub
Actions run directly. It exists to make one canonical local command perform the same lint,
type, smoke, build, metadata, and installed-wheel checks as remote CI. The boundary
optimizes for transparent subprocesses and failure output that can be reproduced locally.

This folder is not for production CLI behavior, deployment, publication, database work, or
feature-specific test modules. Runtime code belongs in `src/vidbyte_cli`; package
publication requires a separate explicitly authorized workflow.

## Blast Radius

`scripts/run_ci.py` is the canonical repository gate and `.github/workflows/ci.yml` invokes
it on every supported platform. A change can decide whether all seven stacked PRs are
mergeable, so steps must remain deterministic and runnable from the repository root.

## Non-Goals

- Do not implement production commands here; `src/vidbyte_cli` owns the installed package.
- Do not publish to PyPI; publication is outside the approved program.
- Do not deploy backend or frontend services; this repository is a client package.
- Do not add feature test packs; the approved no-tests design explicitly excludes them.
- Do not require live Vidbyte credentials or network API calls for verification.
- Do not mutate user configuration or credential stores during smoke checks.
- Do not hide failing subprocess output; the invoking developer needs the original signal.
- Do not duplicate CI step lists in workflow YAML; `run_ci.py` is the canonical sequence.

## File Index

- `run_ci.py` - Runs lint, formatting, strict typing, byte compilation, offline smoke checks,
  package build, metadata validation, and a clean-wheel install check. Open this when
  changing the repository-wide merge gate. Keep every step runnable on Windows, macOS, and
  Linux.
- `smoke.py` - Launches the package through its public module entry point and verifies that
  representative static and harness help screens build without credentials or network
  access. Open this when the public command tree changes. It intentionally proves startup,
  not feature correctness.

## Logs

- 2026-07-26 - Centralized local and remote verification in run_ci.py - prevents workflow and developer checks from drifting.
- 2026-07-26 - Kept verification credential-free - help, version, and packaging remain safe in clean environments.
