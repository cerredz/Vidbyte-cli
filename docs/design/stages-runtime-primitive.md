# Design Doc: Stages Runtime Primitive (`runtime.stages@1`)

**Status:** Proposed
**Author:** vidbyte-cli agent
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

Add `vidbyte-cli runtime stages`, a local runtime primitive that runs a multi-stage skill (for example a design-doc flow: audit, design, implement, verify) with one fresh `CodexHarnessAgent` per stage instead of one agent for all stages. The caller passes a `stages[]` array where entry `i` is the full agent configuration for the agent that runs stage `i`, plus a `parallel` flag that defaults to sequential execution. The invocation costs a flat one-cent admission (`runtime.stages@1`), verified through the existing layered admission gateway before any agent starts.

## 2. Goals & Non-Goals

### Goals

- Add a `stages` command group under the existing `runtime` group with subcommands an agent can discover via `--help`: `run` (priced), plus offline `add`, `list`, `describe` helpers that show every customizable knob.
- Expose per-stage settings that map 1:1 to `CodexHarnessAgentSettings`: identity/prompting (`name`, `system_prompt`, `prompt`, `additional_context`, `output_schema`), thread/turn controls (`model`, `effort`, `summary`, `sandbox`, `approval`, `personality`, `service_tier`, `cwd`), input modalities (text, image, local-image, skill, mention), and Codex-owned subagents (`enabled`, `max_threads`, `default_model`, `default_effort`, `roles`).
- Run each stage on a **new** `CodexHarnessAgent` (never reuse or fork one agent across stages). Sequential mode feeds stage `i-1` output into stage `i` via a `{{previous}}` placeholder; parallel mode runs all stages with `asyncio.gather` and fans results in.
- Wire paid admission exactly like persistence: plan, prepare SDK agents, `admit_stages`, `verify_grant`, `RuntimeAdmissionGate.verify_online`, then `RuntimeExecutor.execute_stages`.
- Keep descriptions agent-rich (every flag explains what it maps to and what values are legal) and keep implementation modular (types, planner, gate, session, executor, commands are separate collaborators).

### Non-Goals

- N/A — there is no deliberate exclusion beyond the list above; every item not listed here is out of scope for this PR.

## 3. Background

Runtime primitives are Vidbyte orchestration algorithms executed through the user's installed coding-agent harness. The CLI owns discovery, admission, launch planning, orchestration, and normalized results; Codex owns its internal model/tool loop (`skills/runtime_primitives/SKILL.md`, `references/runtime-primitives.md`). Persistence (`runtime.persistence@1`, 2c) proved the pattern: `PersistenceCommand` plans, prepares a `CodexHarnessAgent` **before** payment, admits, verifies via `RuntimeAdmissionGate.verify_online`, then executes. Adversarial-team kept the same boundary but stayed inert. Stages reuses that exact gateway and replaces the fixed continuation loop with a caller-defined stage list, which is the missing piece for skills like design-doc that have distinct audit/design/implement phases no single system prompt serves well.

## 4. Requirements

- `R1:` `vidbyte runtime stages run TASK --stages-file FILE [--parallel|--sequential] [--idempotency-key KEY]` plans capability `runtime.stages@1` on host `codex` and charges exactly 1 cent.
- `R2:` Stages file entries validate: `name`/`system_prompt`/`prompt` non-empty; `model`, `effort`, `summary`, `sandbox`, `approval`, `personality` drawn from the SDK enums; at most 10 stages; prompts bounded like tasks (1–20,000 chars).
- `R3:` `stages add/list/describe` are offline (no admission, no agent launch) and round-trip the same schema `run` consumes.
- `R4:` The runner constructs N agents for N stages, enforces completed-status plus non-empty `final_response` per stage, enforces same-thread continuity **within** a stage's single turn, and never shares thread state **across** stages.
- `R5:` Verification order is fixed: idempotency-key format, launch plan, host availability, SDK `prepare()` (free) → `admit_stages` → `verify_grant` → `verify_online` → executor (which re-checks the verdict).
- `R6:` Failures are typed `CliError` subclasses with agent-native `description`/`trace`/`hint`; no module-level helper functions; no model-addressed prose inside `.py` files (stage text comes from the caller).

## 5. High-Level Design

```
stages run TASK
  -> planner.build(task, CODEX, cwd, "runtime.stages@1")   # free validation
  -> StagesCodexSession.prepare(plan, settings)            # build N agents, no turns
  -> endpoints.admit_stages({host}, idempotency-key)       # 1c wallet charge
  -> endpoints.verify_grant({grant_token, sha256(key)})    # backend-canonical receipt
  -> RuntimeAdmissionGate.verify_online(plan, grant, verified)
  -> executor.execute_stages(plan, settings, session, verdict)
       -> sequential: await stage 0, substitute {{previous}}, await stage 1, ...
       -> parallel: await asyncio.gather(*stages)
  -> OutputDocument(kind="runtime.stages", stage_texts, text)
```

Vidbyte owns topology, admission, and result normalization. Codex owns each stage's inner loop. The adapter is a translation boundary: per-stage CLI options become one `CodexHarnessAgentSettings` each.

## 6. Detailed Design

**`types/runtime.py`:** add `"runtime.stages@1"` to the `RuntimeLaunchPlan.capability_id` literal; add frozen `StageEffort/Sandbox/...` string contracts or reuse plain validated strings; add `StageSpec` (name, prompt, system_prompt, model, effort, summary, sandbox, approval, personality, additional_context, inputs, subagents), `StagesSettings` (`stages: tuple[StageSpec,...]` min 1 max 10, `parallel: bool = False`), `StagesResult` (`stage_texts`, `text`).

**`lib/runtime_primitives/planner.py`:** extend `Product` literal with `"runtime.stages@1"`. No logic change.

**`lib/runtime_primitives/gate.py`:** add `"runtime.stages@1": 1` to `_ALLOWED_PRICES`. TTL/policy logic unchanged.

**`lib/api/endpoints/runtime.py`:** add `STAGES_ADMISSION_PATH = "/api/x402/runtime/stages/admissions"` and `admit_stages(request, key)`.

**`lib/constants/runtime.py`:** add `StagesLimit` (`MAX_STAGES=10`, `TURN_TIMEOUT_SECONDS=3600`), `StagesProgress` (PREPARING, CREDENTIALS, ADMISSION one-cent copy, VERIFYING, ADMITTED, STAGE_STARTING, STAGE_COMPLETE, COMPLETE). No secrets or prompt prose here.

**`lib/runtime_primitives/stages.py` (new):** class `StagesCodexSession(environment, progress)` with `prepare(plan, settings)` building `list[CodexHarnessAgent]`, `run(plan, settings)` dispatching to `_run_sequential` / `_run_parallel`, `_turn(agent, prompt)` with `asyncio.timeout`, `_require_completed(reply)` mirroring persistence's status/thread checks, `_to_settings(plan, spec)` translating one spec to `CodexHarnessAgentSettings` (client cwd/bin/env + provider overrides; thread/turn enums; subagents table). Class `StagesFile` with `load(path)` / `append(path, spec)` / `describe(spec)` for the offline subcommands.

**`lib/runtime_primitives/executor.py`:** add `execute_stages(plan, tune, host, proof)` that requires the verdict, checks `capability_id == "runtime.stages@1"` and `host == codex`, then delegates to `host.run`.

**`commands/runtime/stages.py` (new):** class `StagesCommand` registering a `click.Group(name="stages")` with subcommands `run/add/list/describe`. `run` follows `PersistenceCommand.execute` step order exactly (key format `^[A-Za-z0-9._:-]{8,128}$`, plan, settings load, credentials sanitize with empty-override + `OPENAI_API_KEY` inject, prepare, admit, token check, verify, verdict check, execute, `OutputDocument(kind="runtime.stages")`). `add` appends one stage from flags; `list` prints index/name/model/effort/sandbox; `describe` prints every tunable with SDK mapping and legal values.

**`lib/errors/failures.py`:** add `StagesHostFailed` and `StagesSettingsInvalid` as `CliError` subclasses (static prose only).

## 7. Data Model Changes

N/A - no persisted DTOs change. `StagesSettings`/`StagesResult` are local-only frozen pydantic models like `PersistenceSettings`; the wire admission request/grant shapes are reused unchanged.

## 8. API Changes

One new client method: `RuntimeEndpoints.admit_stages` → `POST /api/x402/runtime/stages/admissions` (backend PR ships first per the research-only-surface rule). No change to `verify_grant` or catalog-read paths.

## 9. File Change Manifest

- Create: `docs/design/stages-runtime-primitive.md`, `src/vidbyte_cli/commands/runtime/stages.py`, `src/vidbyte_cli/lib/runtime_primitives/stages.py`, `scripts/test-stages-primitive.py`.
- Modify: `src/vidbyte_cli/types/runtime.py`, `src/vidbyte_cli/lib/runtime_primitives/{planner,gate,executor,__init__}.py`, `src/vidbyte_cli/lib/api/endpoints/runtime.py`, `src/vidbyte_cli/lib/constants/runtime.py`, `src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/commands/runtime/__init__.py`, `src/vidbyte_cli/cli.py` (register group if commands are statically listed there).
- Delete: none. Count: 4 create, ~9 modify, 0 delete.

## 10. Testing Plan

- [Edge Case] Empty stages file (0 stages) is rejected before planning with usage error.
- [Edge Case] 11 stages rejected at `max_length=10`; 10 stages accepted.
- [Edge Case] Blank stage prompt and blank system_prompt each rejected without admission.
- [Edge Case] `{{previous}}` in stage 0 resolves to the top-level task, not empty.
- [Hidden Failure] Backend grant for `runtime.persistence@1` presented to a stages plan yields `CAPABILITY_MISMATCH` and no agent runs.
- [Hidden Failure] Grant charged 2c instead of 1c yields `PRICE_MISMATCH` and no agent runs.
- [Hidden Failure] Mid-sequence stage failure (timeout/non-completed status) stops later sequential stages; parallel collects per-index errors.
- [Silent Failure] Stage output written to the wrong index (off-by-one fan-in) is caught by index-asserted result assembly test.
- [Silent Failure] Cross-stage thread reuse (same thread_id twice) is rejected; each stage must present a distinct thread.
- [Hidden Assumption] SDK missing (`vidbyte-sdk[codex]` not installed) fails during `prepare()` before admission.
- [Hidden Assumption] Idempotency-key reuse returns the same admission without double charge (hash binding test).
- Verification: `scripts/test-stages-primitive.py` runs every case above with PASS/FAIL per case plus `X/Y tests passed`, exit non-zero on failure; then `python scripts/run_ci.py` must exit 0.

## 11. Dependencies

- Backend `POST /api/x402/runtime/stages/admissions` at 1c must be live before `run` ships (CLI never answers "not implemented yet").
- `vidbyte-sdk[codex]` pinned `openai-codex 0.147` for `CodexHarnessAgent`, `CodexHarnessAgentSettings`, `CodexRunInput`; no new Python dependencies.
- Field-guide constraints: runtime-execution (fresh agents, env-merge emptying, verify-before-run), typed-failures (subclass-per-failure, no slop functions), agent-stage-prompts (no model prose in `.py`).

## 12. Rollout

Land backend PR first, then CLI PR. CLI rollout is additive: no existing command changes behavior; `runtime list` picks up the new catalog entry automatically. Docs: `--help` copy is the primary documentation; README command reference updated if it enumerates runtime verbs.

## 13. Open Questions

- Should parallel mode support a fan-in summarizer stage, or return the joined texts and let the caller summarize? (Default: joined texts; summarizer is a follow-up.)
- Should per-stage `model`/`effort` allow a stage to pin `full-access`, or should the CLI cap stages at `workspace-write` like persistence? (Default: allow all three SDK values; sandbox remains Codex-enforced.)

## 14. Alternatives Considered

- **One agent with fork per stage:** rejected — forks inherit thread history, which reintroduces the context pollution stages exists to avoid, and `output_schema` is agent-scoped so mixed shapes need separate agents anyway.
- **Single `--stages-file` flag without subcommands:** rejected — the request explicitly asks for discoverable subcommands so agents see every tunable in `--help`.
- **Backend-executed stages:** rejected — runtime primitives execute caller-locally under caller credentials by design; the backend only admits and verifies.
