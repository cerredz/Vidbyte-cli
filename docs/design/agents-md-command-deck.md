# Design Doc: AGENTS.md Developer Command Deck

**Status:** Draft
**Author:** opencode (design-doc-no-tests workflow)
**Created:** 2026-08-17
**Last Updated:** 2026-08-25

---

## 1. Overview

Add a **Command Deck** section to the root `AGENTS.md`: the verified commands an agent needs to develop, debug, and verify this Python repository, so no session is spent guessing the toolchain. Each entry is the literal command, a 1-2 sentence description, and the command's key parameters. The deck covers fast feedback, targeted diagnostics, packaging checks, and the canonical CI gate.

## 2. Goals & Non-Goals

### Goals
- One top-level `## Command Deck` section appended to `AGENTS.md`, after the File Index.
- Subsections: Fast feedback, Targeted diagnostics, and Packaging checks.
- Every entry: actual command + 1-2 sentences + key params.
- Every command verified against `pyproject.toml`, `scripts/run_ci.py`, the targeted diagnostic scripts, and the `src/` layout.

### Non-Goals
- No changes to any file other than `AGENTS.md` and this design doc.
- No changes to the Map (File Index) content or conventions.
- No package-install instructions or end-user CLI command reference; `README.md` remains the authority for those.

## 3. Background & Context

`AGENTS.md` is already on `main` (PR #19), so this branch cuts from `main` directly. The repository uses a Python 3.11+ `src/` layout, Ruff, strict mypy, byte compilation, script-based offline and loopback diagnostics, `build`, and Twine. `scripts/run_ci.py` is the single canonical gate with no stage selector; it runs the fast checks, targeted diagnostics, distribution validation, and clean-wheel smoke checks in one sequence.

## 4. Requirements

### Functional Requirements
1. `AGENTS.md` gains exactly one new top-level section, `## Command Deck`, placed after the File Index.
2. The section opens with a one-paragraph note stating that it is a developer command reference deliberately outside the Map's topology contract.
3. The deck documents the configured fast-feedback commands: Ruff lint, Ruff format checking, strict mypy, and byte compilation.
4. The deck documents the targeted offline/loopback scripts and the package import/command-tree diagnostics.
5. The deck documents local distribution build and Twine metadata checks.
6. The deck ends with `python scripts/run_ci.py` as the one full repository gate and states that it has no stage selector.

### Non-Functional Requirements
- Scannable entries: command line, at most two sentences, one params line.
- Correct GitHub Markdown rendering; no encoding hazards.

## 5. High-Level Design

Appended content, not Map content; the Map blockquote is untouched and the deck carries its own scope note. Entries are ordered from fast feedback to targeted diagnostics to packaging and the full gate, because an agent can stop at the narrowest useful check while iterating.

```
AGENTS.md
  ...existing Map...
  ## Command Deck        <- new
    ### Fast feedback
    ### Targeted diagnostics
    ### Packaging checks
```

## 6. Detailed Design

### 6.x AGENTS.md Command Deck section

**File(s):** `AGENTS.md`
**Type:** Modified (append one section)

#### Content decisions
- Fast feedback mirrors the tools configured in `pyproject.toml`: Ruff lint, Ruff formatting, strict mypy, and byte compilation.
- Targeted diagnostics name every script called by `run_ci.py` and add import-path and command-tree checks useful during local debugging.
- Packaging checks document the declared `build` and Twine commands, followed by the single full `run_ci.py` gate.
- End-user CLI verbs and installation steps stay in `README.md`, not this deck.

#### Edge cases
- The deck distinguishes targeted diagnostics from the canonical gate so a passing smoke script cannot be mistaken for a merge-ready verification.
- The import-path diagnostic helps detect stale editable installs in the repository's `src/` layout.

## 7. Data Model Changes

N/A - documentation-only change.

## 8. API Changes

N/A - documentation-only change.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agents-md-command-deck.md` | This design doc |
| MODIFY | `AGENTS.md` | Append the developer Command Deck section |

## 10. Dependencies & External Services

N/A - the deck documents local Python tooling and does not add dependencies or service calls.

## 11. Rollout & Deployment

Docs-only; branches from `main`. No feature flags, no migration.

## 12. Open Questions

- [ ] None blocking.

## 13. Alternatives Considered

### Alternative 1: Distribute commands into Map folder entries
- What: Put commands next to `scripts/` and `src/` entries.
- Why rejected: The Map is topology-only by its own contract; the developer workflow deserves one scoped block of its own.

### Alternative 2: A separate COMMANDS.md
- What: Keep AGENTS.md pure.
- Why rejected: Agents would need a second lookup; the developer deck belongs with the repository map in the agent entry point.

END OF DESIGN DOC TEMPLATE
