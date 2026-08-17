# Design Doc: AGENTS.md Command Deck

**Status:** Draft
**Author:** opencode (design-doc-no-tests workflow)
**Created:** 2026-08-17
**Last Updated:** 2026-08-17

---

## 1. Overview

Add a **Command Deck** section to the root `AGENTS.md`: the verified commands an agent needs to install, verify, and drive this CLI, so no session is spent guessing invocations. Each entry is the literal command, a 1-2 sentence description, and the command's key parameters. The deck covers the repository gates, the pytest suite, the full `vidbyte-cli` command surface (auth, harness, research, config, doctor) and its global options.

## 2. Goals & Non-Goals

### Goals
- One top-level `## Command Deck` section appended to `AGENTS.md`, after the File Index.
- Subsections: Repository gates, Tests, and the `vidbyte-cli` command surface with global options.
- Every entry: actual command + 1-2 sentence description + key params.
- Every command verified against `pyproject.toml`, `scripts/run_ci.py`, `src/vidbyte_cli/cli.py`, and `README.md`.

### Non-Goals
- No changes to any file other than `AGENTS.md`.
- No changes to the Map (File Index) content or conventions.
- No new scripts or CI changes.

## 3. Background & Context

`AGENTS.md` is already on `main` (PR #19), so this branch cuts from `main` directly. The CLI is a Python package installed with `pip install -e ".[dev]"`, gated by a single `python scripts/run_ci.py` (no stage selector), with `scripts/smoke.py` as the targeted diagnostic. The command surface is `vidbyte-cli` with root options `--format`, `--json`, `--profile`, `--no-input`, `--color`, `--debug` that precede any command, and command families `auth` (login, logout, whoami), `research`, `config`, and `doctor`. Caution: a stale local checkout on another branch carries a README with extra `harness`/`connect` verbs that are not on `main`.

## 4. Requirements

### Functional Requirements
1. `AGENTS.md` gains exactly one new top-level section, `## Command Deck`, placed after the File Index.
2. The section opens with a one-paragraph note stating it is a run-command reference, deliberately outside the Map's topology contract.
3. The gates subsection leads with `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`, then `python scripts/smoke.py` as a diagnostic.
4. The deck states the root-option rule: global options precede the command.
5. Every verb the shipped CLI exposes on `main` appears: login, logout, whoami, research start/add/resume/status/watch/threads/thread, config get/set, doctor. (`harness` and `connect` verbs exist only on an open feature branch's README and are deliberately excluded.)
6. `python -m vidbyte_cli` appears as the no-install invocation form.

### Non-Functional Requirements
- Scannable entries: command line, at most two sentences, one params line.
- Correct GitHub Markdown rendering; no encoding hazards.

## 5. High-Level Design

Appended content, not Map content; the Map blockquote is untouched and the deck carries its own scope note. Entries are ordered: gates, tests, then the command surface grouped by family, because an agent's intent maps to a verb family.

```
AGENTS.md
  ...existing Map...
  ## Command Deck        <- new
    ### Repository gates
    ### Tests
    ### vidbyte-cli (root options, auth, research, config, doctor)
```

## 6. Detailed Design

### 6.x AGENTS.md Command Deck section

**File(s):** `AGENTS.md`
**Type:** Modified (append one section)

#### Content decisions
- Gates: single full `run_ci.py` run; `smoke.py` labeled diagnostic-only.
- Tests: whole-suite quiet run, single-module run, and `-k` expression filtering.
- CLI: research verbs presented with their priced-mutation note (idempotency) where `README.md` calls it out; global options presented once with a combined example rather than repeated per entry.
- `python -m vidbyte_cli` documented as equivalent to the console script.

#### Edge cases
- The deck notes that results-only-on-stdout rule applies, so agents pipe output safely.

## 7. Data Model Changes

N/A - documentation-only change.

## 8. API Changes

N/A - documentation-only change.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agents-md-command-deck.md` | This design doc |
| MODIFY | `AGENTS.md` | Append the Command Deck section |

## 10. Dependencies & External Services

N/A - the deck only documents commands that already exist in the repository.

## 11. Rollout & Deployment

Docs-only; branches from `main`. No feature flags, no migration.

## 12. Open Questions

- [ ] None blocking.

## 13. Alternatives Considered

### Alternative 1: Distribute commands into Map folder entries
- What: Put commands next to `scripts/` and `src/` entries.
- Why rejected: The Map is topology-only by its own contract; the CLI surface deserves one table-free block of its own.

### Alternative 2: A separate COMMANDS.md
- What: Keep AGENTS.md pure.
- Why rejected: Agents would need a second lookup; the user explicitly wants the deck inside AGENTS.md.

END OF DESIGN DOC TEMPLATE
