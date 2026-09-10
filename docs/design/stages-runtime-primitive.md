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

- `R1:` `vidbyte runtime stages run TASK --stage-prompt P --stage-system-prompt S [...] [--parallel|--sequential] [--idempotency-key KEY]` plans capability `runtime.stages@1` on host `codex` and charges exactly 1 cent. Stages are described entirely on the command line; there is no stages file.
- `R2:` Stage options validate: `system_prompt`/`prompt` non-empty; `effort`, `summary`, `sandbox`, `approval`, `personality` drawn from CLI-owned enums enforced by `click.Choice`; `image` either a remote URL or a local path; `skill`/`mention` as `NAME=PATH`; `output_schema` parsing as a JSON object; at most 25 stages; prompts bounded like tasks (1–20,000 chars). Every repeated `--stage-*` option is given once per stage or omitted entirely, and a partial list is a typed count mismatch.
- `R3:` `stages describe` is offline (no admission, no agent launch) and names every `--stage-*` option `run` accepts with its legal values.
- `R4:` The runner builds one fresh agent per stage attempt (never reused after a failure), retries each stage 0–3 times (default 1, matching the task board) with 2s/8s/32s backoff plus up to 1s jitter, and fails fast without retry on validation errors and cancellation. It enforces completed-status plus non-empty `final_response` per stage, records one step per attempted stage (`index`, `name`, `status`, `thread_id`, `attempts`, `duration_ms`), honors `stop_on_error` (halt with the completed prefix, or continue with a `Stage N failed.` placeholder), and never shares thread state **across** stages.
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

**`types/runtime.py`:** add `"runtime.stages@1"` to the `RuntimeLaunchPlan.capability_id` literal; add CLI-owned `StageSandbox/StageEffort/StageSummary/StageApproval/StagePersonality` `StrEnum`s that the command layer enforces with `click.Choice`, so the adapter converts by value instead of re-parsing free strings; add `StageSpec` (name, prompt, system_prompt, model, effort, summary, sandbox, approval, personality, additional_context, image, skill, mention, output_schema), `StagesSettings` (`stages: tuple[StageSpec,...]` min 1 max `StagesLimit.MAX_STAGES`, `parallel: bool = False`, `stop_on_error: bool = True`, `max_retries_per_stage: int = 0-3 default 1`), `StageStepResult` (index, name, status, thread_id, attempts, duration_ms), `StagesResult` (`admission_id`, `completed`, `failed`, `steps`, `stage_texts`, `text`).

**`lib/runtime_primitives/planner.py`:** extend `Product` literal with `"runtime.stages@1"`. No logic change.

**`lib/runtime_primitives/gate.py`:** add `"runtime.stages@1": 1` to `_ALLOWED_PRICES`. TTL/policy logic unchanged.

**`lib/api/endpoints/runtime.py`:** add `STAGES_ADMISSION_PATH = "/api/x402/runtime/stages/admissions"` and `admit_stages(request, key)`.

**`lib/constants/runtime.py`:** add `StagesLimit` (`MAX_STAGES=25`, `TURN_TIMEOUT_SECONDS=3600`), `StagesCodexConfig`, `StagesProgress` (PREPARING, CREDENTIALS, ADMISSION one-cent copy, VERIFYING, ADMITTED, STAGE_STARTING, STAGE_RETRYING, STAGE_COMPLETE, COMPLETE). No secrets or prompt prose here.

**`lib/runtime_primitives/stages.py` (new):** class `StagesCodexSession(environment, progress)` with `prepare(plan, settings)` recording launch paths without starting any turn, `run(plan, settings, admission_id)` dispatching to `_run_sequential` / `_run_parallel`, `_run_stage` retrying each stage on a fresh agent with backoff and recording one step per outcome, `_turn(agent, spec, prompt)` building a `CodexRunInput` from text plus the stage's image/skill/mention items under `asyncio.timeout`, `_completed_text`/`_thread_id` mirroring persistence's status/thread checks, `_to_settings(plan, spec)` translating one spec to `CodexHarnessAgentSettings` (client cwd/bin/env + provider overrides; thread/turn enums; `output_schema` object). Cancellation is re-raised, never converted. No file loader: the command layer assembles `StagesSettings` from repeated options.

**`lib/runtime_primitives/executor.py`:** add `execute_stages(plan, tune, host, proof)` that requires the verdict, checks `capability_id == "runtime.stages@1"` and `host == codex`, then delegates to `host.run` with the verified admission id.

**`commands/runtime/stages.py` (new):** class `StagesCommand` registering a `click.Group(name="stages")` with subcommands `run/describe`. `run` follows `PersistenceCommand.execute` step order exactly (key format `^[A-Za-z0-9._:-]{8,128}$`, plan, settings load, credentials sanitize with empty-override + `OPENAI_API_KEY` inject, prepare, admit, token check, verify, verdict check, execute, `OutputDocument(kind="runtime.stages")`). Stages are assembled by position from repeated `--stage-*` options, so occurrence i of every option configures stage i; `describe` prints every option with its legal values. `execute_run` carries a comment per ordered step, enforced by lint rule C002.

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

- [Edge Case] A run with no `--stage-prompt` (0 stages) is rejected before planning with a usage error.
- [Edge Case] 26 stages rejected at `max_length=25`; 25 stages accepted.
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
- **A `--stages-file` JSON document:** shipped in the first revision and rejected in review of PR #36 — an agent driving this CLI has to be able to build a whole staged run from argv without first writing a file to disk, and per-option `--help` text documents the surface better than a schema does.
- **Backend-executed stages:** rejected — runtime primitives execute caller-locally under caller credentials by design; the backend only admits and verifies.
