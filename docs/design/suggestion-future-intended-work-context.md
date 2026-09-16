# Design Doc: Future Intended Work in Suggestion Context

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-16
**Last Updated:** 2026-09-16

---

## 1. Overview

Add `future_intended_work` as a distinct caller-supplied context field for the local suggestion agent. The field records work the caller expects or plans to do next, but has not completed and may not have started. Suggestions will use it to sequence, refine, validate, or de-risk the planned work without presenting it as finished or blindly duplicating it. Existing `completed` and `in_progress` inputs remain unchanged, so this is an additive version-1 contract change.

---

## 2. Goals & Non-Goals

### Goals

- Accept repeatable `--future-intended-work` values on `agents suggest run`.
- Accept `context.future_intended_work` as a repeatable list in structured `--input` JSON.
- Normalize each value into a labeled `SuggestionContextItem` with a stable context reference and the kind `future-intended-work`.
- Pass planned work distinctly from completed and active work to generation, critique, suppression, missing-context reporting, and deterministic handoff assembly.
- Add `future_intended_work` to every generated handoff so a downstream caller can see the plan the suggestion was based on.
- Preserve the existing `completed` and `in_progress` contracts and contradiction behavior.
- Add offline verification for CLI input, JSON input, prompt context, handoff output, ordering, empty input, and malformed input.

### Non-Goals

- Automatically discovering plans from repository files, Codex history, task boards, or calendars.
- Marking future work as authorized, started, or completed.
- Automatically executing, scheduling, or persisting future work.
- Renaming `completed`, `in_progress`, or any existing context kind.
- Adding a backend endpoint, database field, migration, pricing, or provider capability.
- Treating future work as a hard exclusion in the same way as completed work; the agent may recommend a prerequisite, refinement, validation step, or better ordering.

---

## 3. Background & Context

- The suggestion agent already accepts narrow context fields such as `completed`, `in_progress`, `decision`, and `constraint`, then converts them into generic `SuggestionContextItem` records.
- Completed work answers “what is already done?” and active work answers “what is underway?” Neither expresses the caller’s intended next sequence, which makes suggestions repeat or ignore planned work.
- The existing handoff already carries completed and in-progress state. Adding planned state beside those fields gives downstream agents enough information to distinguish facts, active work, and intentions.
- The command is local and free. Its strict request boundary, bounded context snapshot, packaged prompts, and deterministic handoff are the relevant architectural constraints.
- The change follows the repository field guide: context travels through the typed request, model-facing prose remains in packaged Markdown, and the CLI validates caller mistakes before provider work.

---

## 4. Requirements

### Functional Requirements

1. `agents suggest run --future-intended-work "..."` accepts the option repeatedly, preserving occurrence order.
2. A structured input document may contain `"context": {"future_intended_work": ["...", "..."]}`; the field is optional and may be omitted.
3. Each nonblank value becomes one `SuggestionContextItem` with kind `future-intended-work`, source `flag:future-intended-work`, `caller_supplied=true`, and a deterministic per-run `ctx-NNN` reference.
4. A present `future_intended_work` value must be a JSON list of strings. A scalar, object, null, or list containing a non-string fails before a model call with the existing typed input error.
5. Prompt assets must define future intended work as planned state, explicitly separated from completed and in-progress state; the current offline template path must preserve that context for handoff and selection, while a provider-backed path can render it into model turns.
6. Suggestions may build on future intended work by proposing prerequisites, sequencing, validation, risk reduction, or a material refinement; they must not claim the planned work is completed.
7. Exact duplicate planned-work statements are not returned as new suggestions unless the suggestion is a clearly labeled prerequisite, validation, or refinement; semantic overlap remains a critic decision, not a substring-only exclusion.
8. Every final `SuggestionHandoff` includes `future_intended_work` in input order and includes it in the current-state rendering.
9. The result context manifest includes future-intended-work entries without exposing full bodies by default.
10. Omitted future intended work remains “not supplied”; it is not represented as an empty user statement and does not generate a warning by itself.
11. Existing `completed`/`in_progress` inputs, including their contradiction warning, continue to behave exactly as before.
12. JSON and human CLI output continue to follow the existing result envelope and stdout/stderr contracts.

### Non-Functional Requirements

- No additional provider calls, network routes, persistence, or dependencies.
- Context handling remains bounded by the existing per-file and total context limits.
- The new field must be available in dry-run output and must not require credentials.
- The public input change is additive and schema-version compatible with `schema_version: 1`.
- Prompt text must be packaged in the wheel and loaded through the existing prompt library.
- Verification must pass `python scripts/test_suggestions.py` and the canonical `python scripts/run_ci.py` gate.

---

## 5. High-Level Design

The command layer adds one repeatable option and one structured-input key. Both paths feed the existing field-to-kind mapping, so the context builder does not need a second storage model. The new kind is `future-intended-work`, which keeps it distinguishable from the existing `completed` and `in-progress` kinds while retaining stable references and manifest behavior.

The prompt contract will define the new kind as planned, uncompleted work. The current service deliberately uses a deterministic offline template path, so it does not make a model turn; it preserves the planned context in selection and handoffs, and the packaged generator/critic prompts are ready for the provider-backed path. Deterministic selection will suppress only exact duplicate planned statements; the critic remains responsible for deciding whether an overlapping proposal is a useful prerequisite, validation, or refinement when that path is active.

The handoff model and renderer will carry the planned statements in a dedicated `future_intended_work` tuple. Its state summary will say that the entries are intended rather than completed, which prevents a downstream executor from treating an intention as a fact. No execution authority is inferred from the field.

```text
[--future-intended-work / input.context.future_intended_work]
                         |
                         v
              [suggest command request boundary]
                         |
                         v
             [SuggestionContextBuilder]
              kind=future-intended-work
                         |
                         v
                [SuggestionRequest]
                  context_items
                 /      |       \
                v       v        v
          [generator] [critic] [handoff]
                \       |        /
                 \      v       /
                   [SuggestionResult]
```

---

## 6. Detailed Design

### 6.1 Command Input Boundary

**File(s):** `src/vidbyte_cli/commands/agents/suggest.py`
**Type:** Modified

#### What it does

Adds the CLI and structured-input representations of future intended work and validates their shape before service execution.

#### Interface / API

```python
@click.option("--future-intended-work", "future_intended_work", multiple=True, help=...)
context.future_intended_work: list[str]
```

#### Logic / Algorithm

1. Define four-sentence caller-facing help explaining that values are planned, not completed, and may guide sequencing or refinement.
2. Include the option in mixed-input rejection so `--input` cannot be combined with it.
3. Include `future_intended_work` in structured-document merging.
4. Validate a present JSON value as a list of strings before converting it to the internal raw mapping.
5. Map the raw field to the `future-intended-work` context kind.

#### Edge Cases & Error Handling

- Omitted option or key produces no context item.
- Empty list is accepted as no supplied entries; blank strings fail through the existing context-item validation path rather than becoming empty context.
- Scalar, object, null, or mixed-type lists raise `SuggestionInputInvalid` before any provider work.
- Existing input exclusivity and schema-version errors remain unchanged.

### 6.2 Typed Suggestion Contracts

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Extends the versioned handoff contract with planned work while retaining the generic request context model.

#### Interface / API

```python
class SuggestionHandoff(BaseModel):
    future_intended_work: tuple[str, ...] = ()
```

#### Logic / Algorithm

1. Add the tuple beside `completed_work` and `in_progress_work`.
2. Keep `extra="forbid"`, frozen models, and existing length constraints.
3. Do not add a separate `SuggestionRequest.future_intended_work`; `context_items` remains the single request context source of truth.

#### Edge Cases & Error Handling

- Missing field deserializes to an empty tuple for backward compatibility with existing handoff files.
- Non-string or oversized values fail Pydantic validation like other handoff context fields.
- Existing result and handoff envelope kinds remain unchanged.

### 6.3 Context Mapping and Manifest

**File(s):** `src/vidbyte_cli/services/suggestions/context.py`
**Type:** Modified if needed for explicit kind handling; otherwise covered by existing generic builder behavior

#### What it does

Keeps future intended work as separate, ordered context items with the existing hashes, refs, and caller-supplied markers.

#### Interface / API

```python
SuggestionContextBuilder.build(fields, files) -> ContextSnapshot
```

#### Logic / Algorithm

1. Reuse the existing generic field iteration for `future-intended-work`.
2. Ensure the manifest records the same kind and source for every entry.
3. Do not merge planned work into general context prose or completed work.

#### Edge Cases & Error Handling

- Multiple values retain input order and receive unique refs.
- Omission produces no fabricated “none” item.
- Existing size caps and contradiction checks remain unchanged.

### 6.4 Generator and Critic Prompt Context

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/generator.md`, `src/vidbyte_cli/services/suggestions/prompts/critic.md`, `src/vidbyte_cli/services/suggestions/prompts/library.py`, `src/vidbyte_cli/services/suggestions/service.py`
**Type:** Modified

#### What it does

Makes the model-facing stages understand the difference between intended plans and completed facts.

#### Interface / API

```python
SuggestionPrompts.generator_turn(goal, categories, context, count) -> str
SuggestionPrompts.critic_turn(goal, candidates) -> str
```

#### Logic / Algorithm

1. Label each planned statement as `Future intended work` in the packaged prompt contract.
2. Tell the generator to use those statements for sequencing, prerequisites, validation, and material refinements when a provider-backed turn is enabled.
3. Tell the generator not to report planned work as completed or simply echo it as a new idea.
4. Tell the critic to distinguish a useful prerequisite/refinement from a duplicate.
5. Preserve separate generator and critic histories and existing output schemas.

#### Edge Cases & Error Handling

- No planned work leaves the prompt section absent or explicitly “not supplied,” consistent with existing context behavior.
- Contradictory completed/in-progress statements remain warnings; future intent does not resolve or hide them.
- Prompt assets remain loadable from an installed wheel.

### 6.5 Selection and Handoff Assembly

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`, `src/vidbyte_cli/services/suggestions/selection.py`, `src/vidbyte_cli/services/suggestions/handoff.py`
**Type:** Modified

#### What it does

Carries planned work into final state and prevents exact echo suggestions without blocking useful next-step reasoning.

#### Interface / API

```python
SuggestionHandoffBuilder.build(idea, goal, context) -> SuggestionHandoff
SuggestionHandoffBuilder.render_prompt(handoff) -> str
```

#### Logic / Algorithm

1. Group context items by kind as the service already does.
2. Copy `future-intended-work` into `SuggestionHandoff.future_intended_work` in original order.
3. Include it in the state summary with explicit “intended” wording.
4. Keep completed/in-progress/avoid/previous-suggestions suppression semantics unchanged.
5. Add an exact normalized duplicate check for planned statements only; leave semantic overlap to the critic.
6. Re-render `execution_prompt` from the structured handoff fields.

#### Edge Cases & Error Handling

- A useful prerequisite or validation step is retained even if it references a planned item.
- An exact echo of a planned item is removed or marked as a shortfall according to existing selection behavior.
- Empty planned work does not create an empty line or false state claim in the handoff.

### 6.6 Documentation and Verification

**File(s):** `README.md`, `src/vidbyte_cli/commands/agents/README.md`, `src/vidbyte_cli/services/suggestions/README.md`, `scripts/test_suggestions.py`
**Type:** Modified

#### What it does

Documents the input shape and verifies the feature through the existing deterministic suggestion-agent script.

#### Interface / API

```text
python scripts/test_suggestions.py
```

#### Logic / Algorithm

1. Add a copyable CLI and JSON example.
2. Extend the context and handoff descriptions.
3. Add labeled checks for every requirement category in Section 10.
4. Keep the test script offline and provider-independent.

#### Edge Cases & Error Handling

- Any failed case exits non-zero and prints its label.
- The final summary reports passed/total counts.
- Documentation describes omission and type errors without implying automatic execution.

---

## 7. Data Model Changes

### 7.1 SuggestionHandoff

**Change type:** Modified

```python
future_intended_work: tuple[str, ...] = ()
```

**Migration strategy:**

- Forward migration: new handoffs include the field when supplied; old handoff JSON remains readable because the field defaults to an empty tuple.
- Rollback plan: remove the new input flag and handoff field; callers that use the new field would need to stop sending it before rollback. No database rollback is required.

### 7.2 Suggestion Context Input Schema v1

**Change type:** Modified additively

```json
{
  "schema_version": 1,
  "goal": "Improve onboarding",
  "context": {
    "future_intended_work": [
      "Interview five new users",
      "Prototype a shorter setup flow"
    ]
  }
}
```

**Migration strategy:** Existing documents remain valid because the field is optional. No schema-version increment is required for an additive optional field.

---

## 8. API Changes

N/A - this is a local CLI and in-memory/file contract change. No backend endpoint, HTTP request, database API, or paid admission route changes.

### 8.1 CLI option

**Change type:** New

```text
vidbyte-cli agents suggest run --goal "..." --future-intended-work "..."
```

The option is repeatable and can be supplied more than once. It is mutually exclusive with `--input` for the same reason as the existing context flags.

### 8.2 Structured input field

**Change type:** New optional field

```json
{
  "context": {
    "future_intended_work": ["string - planned but not completed work"]
  }
}
```

Malformed values fail locally with the existing input-invalid error contract; there is no HTTP status mapping.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-future-intended-work-context.md` | Source-of-truth design for the additive context field |
| MODIFY | `src/vidbyte_cli/commands/agents/suggest.py` | Add CLI option, structured-input key, validation, and field mapping |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add planned-work field to `SuggestionHandoff` |
| MODIFY | `src/vidbyte_cli/services/suggestions/context.py` | Preserve explicit future-intended-work kind behavior if generic mapping needs a guard |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Render planned context and carry it into selection/handoff state |
| MODIFY | `src/vidbyte_cli/services/suggestions/selection.py` | Avoid exact planned-work echoes while retaining useful refinements |
| MODIFY | `src/vidbyte_cli/services/suggestions/handoff.py` | Populate and render `future_intended_work` |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/generator.md` | Define planned-work generation semantics |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | Define duplicate versus prerequisite/refinement review |
| MODIFY | `README.md` | Document CLI and JSON input examples |
| MODIFY | `src/vidbyte_cli/commands/agents/README.md` | Document agent command context behavior |
| MODIFY | `src/vidbyte_cli/services/suggestions/README.md` | Document service-level state distinctions |
| MODIFY | `scripts/test_suggestions.py` | Add deterministic edge, failure, silent-failure, and assumption checks |

No files are deleted. No migration, dependency, or package-data change is expected because existing prompt files and package globs are reused.

---

## 10. Testing Plan

### Unit Tests

- `[Edge Case]` One `--future-intended-work` value becomes one `future-intended-work` item with a stable `ctx-001` ref.
- `[Edge Case]` Multiple values retain order in context items, manifest entries, grouped service context, and handoff output.
- `[Edge Case]` Omitted option and omitted JSON key produce no planned-work item and no false “none” statement.
- `[Edge Case]` An empty list is treated as no supplied planned work.
- `[Hidden Failure]` A JSON scalar, object, null, or mixed-type list fails before service/model execution.
- `[Hidden Assumption]` Existing context fields retain their prior string-coercion behavior when a legacy document contains scalar list items.
- `[Hidden Failure]` A planned statement is not accidentally assigned the `completed` or `in-progress` kind.
- `[Hidden Failure]` Existing completed/in-progress contradiction warnings still appear when future intent is also supplied.
- `[Silent Failure]` `SuggestionHandoff.future_intended_work` contains the original values rather than an empty tuple or a reordered set.
- `[Silent Failure]` Current-state text says “intended” or equivalent and does not claim planned work is completed.
- `[Silent Failure]` Exact planned-work echoes are suppressed while a prerequisite or validation suggestion remains eligible.
- `[Hidden Assumption]` A legacy handoff without `future_intended_work` still validates and loads with an empty tuple.
- `[Hidden Assumption]` The feature works in `--dry-run` mode without credentials or SDK imports.
- `[Hidden Assumption]` Prompt assets load from the installed wheel, not only from the repository working directory.

### Integration Tests

- Run the CLI with repeated `--future-intended-work` flags and inspect JSON output for manifest and handoff state.
- Pipe structured JSON through `--input -` and verify the same result shape as the flag path.
- Combine `--input` with `--future-intended-work` and verify the existing mutual-exclusion error.
- Run `python scripts/test_suggestions.py` with no provider credentials; all cases must pass offline.
- Run `python scripts/run_ci.py` to cover lint, formatting, strict typing, compile, smoke, build, and clean-wheel checks.

### Manual / QA Test Cases

1. Given a goal and two future intended work statements, run `agents suggest run --dry-run`; then verify the manifest exposes two labeled refs and no model call is required.
2. Given a JSON input document containing `context.future_intended_work`, run through stdin; then verify the human output describes planned state separately from completed state.
3. Given a planned item that is not complete, generate suggestions; then verify the agent may propose a prerequisite or validation step but does not present the planned item as completed.
4. Given an invalid scalar `future_intended_work`, run the command; then verify a typed input error appears on stderr and stdout remains result-only.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | CLI and typed contracts | Existing runtime constraint; no change |
| Click | `>=8.1,<9` | Repeatable CLI option and validation | Existing dependency; no new risk |
| Pydantic | `>=2.6,<3` | Frozen handoff/request validation | Existing dependency; additive optional field |
| Vidbyte SDK | Existing pinned Git revision | Optional provider-backed generation | No new calls or SDK surface |
| Packaged Markdown prompts | Existing setuptools package data | Generator/critic semantics | Wheel packaging must be verified |

---

## 12. Rollout & Deployment

- No feature flag is needed because the field is optional and additive.
- Land the design doc and implementation on a branch based on the live suggestion-agent branch, then target that branch’s integration path.
- Existing callers require no migration. New callers can adopt the field when the CLI version containing it is available.
- Rollback is a code rollback: stop sending the new option/key, then revert the implementation commit. Existing completed/in-progress callers remain valid.
- Before handoff, run the deterministic suggestion script and the full CLI gate, including a clean-wheel prompt-asset check.

---

## 13. Open Questions

- [ ] Should the public CLI option also accept a shorter alias such as `--future-work`, or should the explicit name remain the only spelling?
- [ ] Should future intended work appear as a separate top-level `SuggestionResult` summary in addition to each handoff, or is the manifest plus handoff sufficient for v1?
- [ ] For semantic overlap, should a future planned item be treated as a soft penalty in the critic or only as context for sequencing and prerequisite generation?

---

## 14. Alternatives Considered

### Alternative 1: Reuse `completed`

- What: Put planned work into the existing completed list.
- Why rejected: It lies about task state and causes the generator to suppress useful prerequisites or refinements.

### Alternative 2: Reuse `in_progress`

- What: Treat all intended work as already underway.
- Why rejected: Intentions may be tentative or blocked, and downstream agents would infer active ownership that the caller did not grant.

### Alternative 3: Add a separate top-level `SuggestionRequest.future_intended_work`

- What: Store the new field beside `context_items`.
- Why rejected: It creates two sources of truth and bypasses the existing context refs, manifest, hashing, and common prompt rendering path.

### Alternative 4: Make planned work a hard suppression list

- What: Reject every suggestion that overlaps a planned item.
- Why rejected: The useful next suggestion is often a prerequisite, validation, sequencing change, or risk-reduction step for that planned item.

