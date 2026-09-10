# Design Doc: Suggestion Agent (Next-Action Specialized Agent)

**Status:** First edition implementation plan
**Author:** opencode (from Codex thread 01a0892a, last model response 2026-09-09)
**Created:** 2026-09-10
**Source of truth:** Codex rollout `2026-09-09T22-34-29` ordinals 131/132 (CLI-first suggestion agent with generator+critic, optional context flags, 17-category registry, structured handoff). If a change is not described here, do not implement it.

---

## 1. Overview

Add `vidbyte-cli agents suggest`, the first specialized (next-action) agent: a locally orchestrated, SDK-powered suggestion workflow that accepts a goal plus optional caller-supplied context and returns ranked ideas with execution-ready handoffs. Commands are `run` (generate/critique/return), `categories` (list registry, no model), and `handoff` (extract one handoff from a saved result, no model). The service is callable as `SuggestionService.run(SuggestionRequest) -> SuggestionResult` with no Click/stdout dependency, leaving a later web endpoint path open. v1 ends at a useful structured handoff; it does not launch work, maintain a board, or add proactive triggers.

## 2. Goals / Non-Goals

### Goals

- Ship `agents suggest run|/categories|handoff` locally in `vidbyte-cli`, agreeing with the Codex thread's CLI-first decision (caller is usually another agent with a task snapshot).
- Accept a nonempty goal via `--goal` or structured `--input` JSON (plus `--input -` for stdin), with generation controls (`--count`, `--category`, `--all-categories`, `--horizon`, `--rounds`, provider/model/token/timeout, `--dry-run`).
- Accept all 13 optional context flags from the thread (`--context`, `--context-file`, `--handoff-file`, `--completed`, `--in-progress`, `--decision`, `--constraint`, `--avoid`, `--question`, `--capability`, `--success`, `--artifact`, `--previous-suggestions`), all optional and repeatable (except single-path inputs where noted).
- Own a versioned 17-category registry driving CLI validation, prompt instructions, and schema validation without drift.
- Run generator + independent critic with explicit revise loop in `service.py` using ordinary linear SDK agents, separate histories, bounded candidate pool (2x count, cap 40), selection up to count, deterministic handoff assembly (no `HandoffAgent` formatting call).
- Emit existing envelope (`schema_version`, `kind`, `data`) with `kinds` `suggestions.result` and `suggestions.handoff`; stdout carries results only.
- Make `--help` and `categories` work without credentials; package prompts in the wheel; keep `scripts/run_ci.py` green.

### Non-Goals

- Website UI, automatic execution/launching of suggestions, idea board persistence, proactive triggers — explicitly deferred by the thread to separate measurable additions.
- Automatic repo scanning or Codex history discovery — v1 reads only explicitly supplied files.
- New SDK abstractions, embedding-based dedup, hard shared dollar caps — v1 uses two ordinary agents, critic-based semantic overlap, token/time/round stopping thresholds.
- Backend routes, catalog, pricing, or admission — this agent is local-only and free; no x402 wiring.

## 3. Background

- `vidbyte-cli` is a thin transport/presentation layer (AGENTS.md): stdout-is-results-only, integer-status entry functions, commands orchestrate into `lib/`, feature logic lives in `services/` between commands and `lib/`.
- Existing local services (`ensemble/`, `persistence/`) establish the shape to follow: `runner.py` admission boundary, `session.py` loop, `prompts/` Markdown with a `library.py` loader using literal `{{token}}` replacement and `importlib.resources` (wheel-safe), `sdk.py` as the only module importing `vidbyte-sdk` lazily so `--help` works without it.
- Field guide constraints applied: typed `CliError` subclasses in `lib/errors/failures.py` (no bare constructors, no module-level helper functions, agent-native description/trace); prompts in Markdown (no model-facing sentences in `.py`); closed vocabularies as CLI-owned enums via `click.Choice`; argv-driven config (structured `--input` allowed here because the thread explicitly requires JSON-stdin for agent callers, with mutual-exclusivity rules to keep precedence predictable); 3–6 line module docstrings, no templated headers; package-data globs for every non-Python asset.
- The Codex thread (user ordinals 101–102) asked for: (1) file map + SDK usage, (2) optional context commands, (3) idea categories + structured handoff, (4) CLI-invokable idea count — as a checklist, no code. This doc turns that checklist into the buildable contract.

## 4. Requirements

### Functional Requirements

1. `agents suggest run` requires a nonempty `--goal` (or `goal` in `--input` JSON); `--input` is mutually exclusive with individual goal/context flags; `--count` etc. may override input-document values.
2. `--count` default 5, range 1–20, means "up to N worthwhile ideas": fewer with explicit shortfall is valid; weak filler is not.
3. `--category ID` repeatable restricts generation; unknown IDs fail before model calls; no category flags means consider the whole registry and select a useful mix; `--all-categories` makes that explicit without requiring one idea per category.
4. `--horizon now|next|later|any` default `any`; `--rounds` default 2, range 1–3; `--dry-run` resolves inputs and returns context manifest + settings + warnings with no model call and without dumping full file contents by default.
5. Context inputs: read only explicitly supplied files; UTF-8 text/Markdown + documented JSON schemas; reject missing files, directories, malformed JSON, unsupported schema versions; stable per-run context refs; preserve source identity (caller-supplied vs artifact-observed); per-file + total limits before model calls; explicit omission/truncation reporting; file contents are data, never instruction overrides; surface contradictions; never infer execution permission.
6. Workflow: validate + resolve context; generate pool up to 2x count capped at 40; critic assesses (relevance, why-now, evidence/assumptions, feasibility/prereqs, overlap, concreteness, recognizability, displacement worth); revise only actionable candidates within round/token/time limits; select up to count; assemble handoffs; emit validated result.
7. Critic identifies duplicates by candidate IDs; exact-duplicate checks in code; semantic overlap via critic (no embeddings v1). Generator/critic histories stay separate; critic sees candidate artifact + supporting context only. Keep earlier versions + last fully reviewed batch for partial-result fallback.
8. Every idea carries one primary + optional secondary categories, horizon, relationship (`direct|alternative|adjacent|exploratory`), readiness (`ready|needs_evidence|needs_decision|blocked`), evidence refs limited to supplied IDs, assumptions/dependencies, first action, completion criteria, review summary, and a full handoff.
9. Handoff fields per thread (handoff_version … execution_prompt); `authority` defaults to `not_granted_by_this_handoff`; `required_context` carries excerpts/summaries + refs (never paths alone); `acceptance_checks` observable; `stop_conditions` include completion/contradiction/missing-authority/missing-prereqs; `execution_prompt` rendered deterministically from structured fields.
10. `categories` and `handoff` extraction make no model calls; `handoff --input result.json --idea idea-003` emits `suggestions.handoff` preserving ID/revision; provider failure never misreports as `no_suggestions`.

## 5. High-Level Design

New `agents` command family (distinct from `runtime` primitives) → `services/suggestions/` workflow → `types/suggestions.py` contracts → `lib/` substrate (output envelope, errors, provider credentials). `sdk.py` lazily constructs generator + critic agents from existing SDK linear-agent surface (`Agent`/`BaseAgent`, `AgentInput`, `TextContextItem`, `output_schema`, usage reporting, token/timeout controls, no execution tools). `service.py` owns the explicit generate→critique→revise→select loop. `selection.py` validates eligibility/ranking/dedup; `handoff.py` assembles handoffs deterministically; `context.py` builds the bounded snapshot; `categories.py` owns the registry; `prompts/` holds generator + critic Markdown. v1 ships a deterministic template-backed generator path so goal-only and offline verification work without credentials, with the SDK path used when provider/model is configured and available.

## 6. Detailed Design

### 6.1 Command surface (`commands/agents/`)

- `__init__.py` registers `agents` group + `suggest` subgroup; `suggest.py` implements `run` with all flags from §§4–5 of the thread (goal, 13 context flags, count/category/horizon/rounds/provider/model/critic-model/token/timeout/dry-run/input); `suggestion_categories.py` renders registry; `suggestion_handoff.py` reads saved result + selects by idea ID; `render.py` produces human-readable results via existing output machinery. All `--help` texts meet the 4-sentence caller-facing floor. `run` validates locally (counts, categories, input exclusivity) before any model/provider work.

### 6.2 Service (`services/suggestions/`)

- `service.py`: `SuggestionService.run(SuggestionRequest) -> SuggestionResult`; orchestrates context → generation → critique rounds → selection → handoff; enforces pool cap (2x count, max 40), round/token/deadline stops, partial-result fallback, usage aggregation, prompt_version stamping; never imports Click.
- `sdk.py`: only module importing `vidbyte-sdk`, lazily inside methods; resolves provider config via existing credential infrastructure; maps CLI provider names to SDK identifiers explicitly; constructs generator/critic with no execution tools; normalizes replies via `AgentMessage.structured`; exposes `is_provider_error`/`is_schema_error` classification following `ensemble/sdk.py`.
- `context.py`: reads explicit files only (context-file/artifact/handoff-file/previous-suggestions/input), enforces UTF-8/Markdown/JSON schemas, size caps, hashing, stable `ctx-N` refs, contradiction surfacing, omission reporting.
- `categories.py`: `SuggestionCategory` StrEnum (17 IDs) + descriptions + generation guidance; single owner for CLI `Choice`, prompt text, and schema validation.
- `selection.py`: eligibility (evidence IDs ⊆ manifest, category validity), ranking, exact-dedup in code, shortfall explanation, `category_coverage` computation.
- `handoff.py`: deterministic assembly + `execution_prompt` rendering from structured fields; `authority` default constant.
- `prompts/library.py` + `prompts/generator.md` + `prompts/critic.md`: literal `{{token}}` replacement, `importlib.resources` loading, no model sentences in `.py`.

### 6.3 Types (`types/suggestions.py`)

Frozen, extra-forbid Pydantic models: `SuggestionRequest`, `SuggestionContextItem`, `ContextManifestEntry`, `SuggestionSettings`, `SuggestionIdea`, `SuggestionHandoff`, `SuggestionResult`; `SCHEMA_VERSION = 1`; kind literals `suggestions.result` / `suggestions.handoff`; horizon/relationship/readiness/status/stop-reason enums owned here.

### 6.4 Errors (`lib/errors/failures.py`)

Add `SuggestionInputInvalid`, `SuggestionCategoryUnknown`, `SuggestionContextUnreadable`, `SuggestionLimitExceeded`, `SuggestionProviderFailed`, `SuggestionNoResult` (each with code/exit/retryable + 3–4 sentence description + trace + hint), reusing existing codes where possible; raise sites stay one-liners.

## 7. Data Model Changes

N/A — no database, migrations, or durable local state. New in-memory/file contracts only: `SuggestionRequest` (input JSON schema v1), `SuggestionResult` (`suggestions.result` v1), `SuggestionHandoff` (`suggestions.handoff` v1). JSON schemas are documented in `README.md` and validated by Pydantic; unsupported `schema_version` is rejected.

## 8. API Changes

N/A — no backend routes, no catalog, no pricing. This is a local-only free workflow: no admission, no idempotency keys, no network calls except the caller's configured model provider via the SDK.

## 9. File Change Manifest

Create (21):

- `docs/design/suggestion-agent.md` (this file)
- `src/vidbyte_cli/commands/agents/__init__.py`
- `src/vidbyte_cli/commands/agents/README.md`
- `src/vidbyte_cli/commands/agents/suggest.py`
- `src/vidbyte_cli/commands/agents/suggestion_categories.py`
- `src/vidbyte_cli/commands/agents/suggestion_handoff.py`
- `src/vidbyte_cli/commands/agents/render.py`
- `src/vidbyte_cli/types/suggestions.py`
- `src/vidbyte_cli/services/suggestions/__init__.py`
- `src/vidbyte_cli/services/suggestions/README.md`
- `src/vidbyte_cli/services/suggestions/categories.py`
- `src/vidbyte_cli/services/suggestions/context.py`
- `src/vidbyte_cli/services/suggestions/service.py`
- `src/vidbyte_cli/services/suggestions/sdk.py`
- `src/vidbyte_cli/services/suggestions/selection.py`
- `src/vidbyte_cli/services/suggestions/handoff.py`
- `src/vidbyte_cli/services/suggestions/prompts/__init__.py`
- `src/vidbyte_cli/services/suggestions/prompts/library.py`
- `src/vidbyte_cli/services/suggestions/prompts/generator.md`
- `src/vidbyte_cli/services/suggestions/prompts/critic.md`
- `scripts/test_suggestions.py`

Modify (7):

- `src/vidbyte_cli/commands/__init__.py` (register `agents`)
- `src/vidbyte_cli/lib/errors/failures.py` (6 failure classes)
- `pyproject.toml` (package-data glob for suggestions prompts)
- `README.md` (commands, inputs, defaults, examples, local semantics)
- `scripts/run_ci.py` (include deterministic verification script)
- `scripts/smoke.py` (registration/help/machine-output checks)
- `scripts/test_research_only_surface.py` (authorize new `agents` family)

Delete (0).

## 10. Testing Plan

Deterministic verification via `scripts/test_suggestions.py` (fakes only at the SDK turn; no live API, no Codex process). Every case labeled:

- [Edge Case] Goal-only run returns 1–5 valid ideas with handoffs, no credentials required.
- [Edge Case] `--count 1` returns exactly ≤1; `--count 20` accepted; `--count 0` and `--count 21` fail before model calls.
- [Edge Case] Empty `--goal ""` and missing goal without `--input` fail before model calls.
- [Edge Case] `--input -` (stdin JSON) works with no interactive prompts under `--no-input`.
- [Edge Case] `--input` combined with `--goal` fails (mutual exclusivity); `--count` overrides input-document count.
- [Edge Case] Unknown `--category nope` fails before model calls; `--all-categories` with no `--category` considers full registry.
- [Hidden Failure] Completed/avoid/previous-suggestions content suppresses or penalizes overlapping ideas (caller supplies "dashboard rejected" → no dashboard idea in top results).
- [Hidden Failure] Malformed `--input` JSON, missing file, directory as file, unsupported `schema_version` each fail with typed errors, no model call.
- [Hidden Failure] Provider failure raises `SuggestionProviderFailed`, never `status=no_suggestions`.
- [Hidden Failure] Evidence refs outside the manifest are rejected by selection (syntactically valid ID ≠ support).
- [Silent Failure] Returned ideas never exceed `--count`; shortfall sets explicit counts + warning instead of weak filler.
- [Silent Failure] Every idea carries a valid handoff; `handoff` extraction preserves idea ID + revision and emits `suggestions.handoff`.
- [Silent Failure] Generator and critic use separate contexts (fake asserts distinct system prompts/histories); `execution_prompt` re-renders from structured handoff fields (mutating a field changes the prompt).
- [Silent Failure] JSON stdout parses as envelope (`schema_version`/`kind`/`data`); diagnostics go to stderr (captured separately).
- [Hidden Assumption] `--help` and `categories` work with no credentials and no SDK import (assumption: provider always configured — violated on purpose).
- [Hidden Assumption] Packaged prompts load from installed wheel path via `importlib.resources` (assumption: cwd-relative reads work — violated by running from another directory).
- [Hidden Assumption] Omitted context means "not supplied", not "none exist": dry-run manifest marks absent sections as `not_supplied` rather than empty (assumption: missing = empty).
- [Hidden Assumption] Token/timeout/round limits cover revisions too: a run with `--rounds 1 --max-total-tokens 1` stops with `partial` + `stop_reason`, not silent truncation.
- [Edge Case] `--dry-run` returns manifest + settings + warnings with no model call and without dumping full file bodies.
- [Hidden Failure] Contradictory context (`--completed X` vs `--in-progress X`) surfaces a warning instead of silently picking one.

Existing gates: `python scripts/run_ci.py` (ruff, format, mypy strict, cli lint suite, compileall, smoke, surface tests, task-board, build/twine/clean-wheel).

## 11. Dependencies

- `vidbyte-sdk` linear agents (`Agent`/`BaseAgent`, `AgentInput`, `TextContextItem`, `output_schema`, usage, timeouts) — verify against the revision pinned in `pyproject.toml`, not just the adjacent checkout; explicit CLI→SDK provider-name mapping; agents configured with no execution tools.
- No new PyPI dependencies; no database/scheduler/broker; stdlib + `click` + `pydantic` only (SDK already pinned).

## 12. Rollout

Land as one PR on `feat/suggestion-agent` → `main` (draft, body = this doc); verify with `scripts/test_suggestions.py` + full `run_ci.py`; follow with a separate usefulness evaluation (real task snapshots: finished/blocked/conflicting/rejected-idea cases; two-agent vs single-call baseline) before any launch/board/trigger follow-ups.

## 13. Open Questions

1. Should `--model`/`--critic-model` accept fully qualified provider model IDs or a curated CLI-owned subset (closed-enum rule favors the latter)?
2. What per-file/total context byte caps should v1 enforce (proposal: 8KB/file, 64KB total, explicit truncation)?
3. Does v1 need `--previous-suggestions` semantic similarity beyond critic review, or is critic + exact-dedup enough for the usefulness eval?

## 14. Alternatives Considered

- **Website-hosted agent first:** rejected for v1 — the thread's caller is an agent with local context; CLI-first gives a bounded snapshot in/out contract to evaluate before any backend work.
- **`runtime` primitive placement:** rejected — `runtime` means paid, admitted, host-delegated execution; this agent is free, local, and returns suggestions without executing them, so a distinct `agents suggest` family avoids overloading admission semantics.
- **`HandoffAgent` for final formatting:** rejected — deterministic assembly from validated fields avoids an extra model call and factual drift.
- **Embedding dedup / hard dollar caps / auto repo scanning:** deferred — critic + code dedup, token/time/round stops, and explicit file inputs are simpler, predictable, and sufficient to test whether another agent can consume the handoff.
