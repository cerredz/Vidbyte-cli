# Design Doc: Suggestion Handoff Context

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

Expand the suggestion agent's structured handoff so an executor receives both the action packet and the reasoning that produced the suggestion. The current handoff contains execution fields, but it drops several fields from `SuggestionIdea` and does not represent the problem, causal rationale, tradeoffs, unknowns, confidence, or expected before-and-after change as typed data. This change adds a bounded `SuggestionContext` contract, copies the existing idea metadata into every handoff, renders the new context deterministically, and validates the result through offline tests. The top-level `suggestions.result` envelope remains version 1; the nested handoff advances to version 2.

---

## 2. Goals & Non-Goals

### Goals

- Add a typed `SuggestionContext` section to each generated idea and handoff.
- Preserve existing suggestion metadata in the handoff: title, summary, categories, horizon, relationship, readiness, benefit, effort, review summary, and evidence refs.
- Represent the suggestion's problem or opportunity, core insight, causal rationale, goal contribution, expected change, beneficiaries, affected surfaces, tradeoffs, risks, unknowns, confidence, alternatives, cost of inaction, reversibility, and time sensitivity.
- Represent a concrete verification plan with a claim, procedure, pass condition, evidence to capture, and failure response.
- Represent scope boundaries and decision points so an executor knows what belongs in the work and how to respond to unresolved conditions.
- Make the deterministic execution prompt expose the context needed to understand and execute the suggestion without reopening the result file.
- Update generator and critic prompts so model-backed candidates provide and review the new context.
- Keep authority, dependency, evidence-reference, stop-condition, and results-only output guarantees intact.
- Bump only `SuggestionHandoff.handoff_version` from 1 to 2 while retaining the top-level result envelope version.
- Add offline tests for every new field, prompt rendering, schema validation, malformed context, boundary values, and wheel packaging of changed prompt assets.

### Non-Goals

- Launching or automatically executing a suggestion.
- Adding a database, persistence, web endpoint, scheduler, or suggestion board.
- Discovering repository facts or history that the caller did not supply.
- Replacing the existing category registry, ranking algorithm, or context-file limits.
- Adding numeric scoring that implies unsupported precision.
- Supporting transparent migration of old handoff-version-1 documents in this change; consumers must inspect `handoff_version` and request a newly generated packet.

---

## 3. Background & Context

- `SuggestionIdea` already carries useful framing fields, but `SuggestionHandoffBuilder` currently copies only a subset into the handoff. The current renderer emits only goal, action, why, state, steps, acceptance checks, stop conditions, authority, and report.
- The current builder also uses `first_action` as the entire selected action, uses `completion_criteria` as both a step and an acceptance check, and maps `expected_benefit` into `deliverables`. This makes the execution packet weaker than the suggestion it represents.
- The repository uses frozen, `extra="forbid"` Pydantic models in `types/suggestions.py`, Markdown prompt assets under `services/suggestions/prompts/`, deterministic handoff assembly in `services/suggestions/handoff.py`, and `scripts/test_suggestions.py` as the offline verification path.
- The field guide requires bounded evidence with stable refs and source context, prompt text in Markdown, sparse non-obvious comments, and the canonical `python scripts/run_ci.py` gate.
- The change must remain local and provider-independent for the deterministic template path. SDK-backed generation will consume the same schema when configured.

---

## 4. Requirements

### Functional Requirements

1. Define frozen, extra-forbid Pydantic models for the structured suggestion context and its nested problem, change, tradeoff, risk, unknown, confidence, alternative, reversibility, and time-sensitivity records.
2. Require every generated `SuggestionIdea` to carry a complete `SuggestionContext` with bounded strings and tuples.
3. Copy the idea's existing metadata and its `SuggestionContext` into every generated `SuggestionHandoff`.
4. Emit `handoff_version=2` for new packets while leaving `SUGGESTIONS_RESULT_KIND`, `SUGGESTIONS_HANDOFF_KIND`, and the top-level `schema_version=1` unchanged.
5. Render all execution-relevant existing handoff fields and all new suggestion-context fields in stable section order.
6. Preserve the invariant that evidence refs are selected from caller-supplied context refs and that the handoff never grants authority.
7. Update the deterministic generator to populate meaningful, non-empty context for every category and goal.
8. Update the generator prompt to require problem/opportunity, insight, rationale, expected change, tradeoffs, risks, unknowns, confidence basis, and verification-ready context.
9. Update the critic prompt to reject unsupported, repetitive, causally incomplete, over-broad, or unverifiable context.
10. Keep the existing handoff extraction command working for newly generated version-2 packets and expose the version in machine-readable output.
11. Add an offline verification script and include it in the canonical CI sequence.
12. Confirm both changed prompt assets are present in the built wheel.

### Non-Functional Requirements

- No provider call, credential lookup, or filesystem write is introduced by handoff construction or extraction.
- Structured fields must remain bounded so a generated handoff cannot grow without limit; rendered prompts must remain within the existing 16,384-character contract.
- Rendering must be deterministic: the same structured handoff produces the same prompt, and changing one field changes the prompt.
- Existing stdout/stderr, JSON-envelope, authority, and typed-validation contracts remain unchanged except for the documented nested handoff version.
- The implementation follows the repository's Python formatting, strict typing, and class/comment conventions.

---

## 5. High-Level Design

Add a small family of immutable nested models in `types/suggestions.py`. `SuggestionContext` aggregates the suggestion's existing explanatory metadata and the new structured context dimensions. `SuggestionIdea` owns one context object, while `SuggestionHandoff` copies that object together with the existing execution fields and the idea metadata that was previously omitted.

The deterministic service populates the context from the goal, category, supplied context refs, and the template's bounded assumptions. The handoff builder remains the single assembly boundary: it maps idea fields, adds caller state, and renders the prompt only after the complete model validates. The renderer will expose the context before execution steps so an agent can understand the proposal before acting.

The Markdown generator and critic prompts will describe the same contract for provider-backed runs. Tests will exercise the deterministic service, builder, renderer, extraction shape, invalid nested data, prompt mutation, and wheel contents. No new runtime service or external dependency is needed.

```text
[goal + caller context]
          |
          v
 [SuggestionService generator]
          |
          v
 [SuggestionIdea + SuggestionContext]
          |
          v
 [SuggestionHandoffBuilder]
          |  validates, copies, renders
          v
 [SuggestionHandoff v2 + execution_prompt]
```

---

## 6. Detailed Design

### 6.1 Structured suggestion context models

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Defines the typed context behind a suggestion. Each nested model uses frozen, extra-forbid Pydantic configuration and bounded fields. Literal values are used for small closed vocabularies so malformed model output fails validation instead of becoming ambiguous prose.

#### Interface / API

```python
class SuggestionContext(BaseModel):
    problem_or_opportunity: SuggestionProblem
    core_insight: str
    causal_rationale: str
    goal_contribution: SuggestionGoalContribution
    expected_change: SuggestionExpectedChange
    scope: SuggestionScope
    decision_points: tuple[SuggestionDecisionPoint, ...]
    verification_plan: tuple[SuggestionVerification, ...]
    final_success_condition: str
    beneficiaries: tuple[str, ...]
    affected_surfaces: tuple[str, ...]
    tradeoffs: tuple[SuggestionTradeoff, ...]
    risks: tuple[SuggestionRisk, ...]
    unknowns: tuple[SuggestionUnknown, ...]
    confidence: SuggestionConfidence
    alternatives_considered: tuple[SuggestionAlternative, ...]
    cost_of_inaction: str
    reversibility: SuggestionReversibility
    time_sensitivity: SuggestionTimeSensitivity
```

`SuggestionHandoff` gains the existing idea metadata fields plus `suggestion_context: SuggestionContext`, and its `handoff_version` becomes the literal value `2`. `SuggestionIdea` gains the same `suggestion_context` field.

#### Logic / Algorithm

1. Validate every nested record before a model call result reaches selection or handoff assembly.
2. Keep evidence references as the existing `evidence_refs` tuple; the context explains the claim but cannot mint a new ref.
3. Require at least one in-scope item, out-of-scope item, decision point, beneficiary, affected surface, tradeoff, risk, unknown, alternative, verification check, and confidence basis in the deterministic path; optional conceptual cases may use explicit “none identified” records rather than empty meaning.
4. Keep enum values general enough for non-software suggestions: problem/opportunity, low/medium/high likelihood and impact, low/medium/high time sensitivity, and reversible/partly-reversible/hard-to-reverse.

#### Edge Cases & Error Handling

- Empty required strings, unsupported literals, extra keys, overlong values, and invalid tuple members fail Pydantic validation.
- A goal-only deterministic run still receives explicit “caller context not supplied” assumptions and unknowns; it never fabricates evidence refs.
- Old nested handoff version 1 is rejected by the version-2 model with a typed validation failure during extraction.

### 6.2 Suggestion generation and review

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`
**Type:** Modified

#### What it does

Populates the new context for deterministic candidates and preserves it through critique, selection, and handoff rebuilding.

#### Interface / API

```python
class SuggestionService:
    def run(self, request: SuggestionRequest) -> SuggestionResult: ...
```

#### Logic / Algorithm

1. Derive a stable context object from the goal, category, current caller state, and the first allowed evidence ref.
2. Add the context to each generated `SuggestionIdea` alongside existing fields.
3. Keep critique updates limited to review metadata so context remains attached to the candidate that was reviewed.
4. Pass the final idea context to `SuggestionHandoffBuilder`, which performs the final typed copy.

#### Edge Cases & Error Handling

- Goal-only runs use explicit bounded assumptions and unknowns instead of empty context.
- Context refs remain empty when no caller context exists, and selection continues to reject any invalid ref.
- The candidate pool and requested-count limits remain unchanged.

### 6.3 Deterministic handoff assembly and rendering

**File(s):** `src/vidbyte_cli/services/suggestions/handoff.py`
**Type:** Modified

#### What it does

Builds a version-2 handoff and renders a deterministic, copyable prompt that contains both suggestion reasoning and execution instructions.

#### Interface / API

```python
class SuggestionHandoffBuilder:
    def build(
        self, idea: SuggestionIdea, goal: str, context: dict[str, tuple[str, ...]]
    ) -> SuggestionHandoff: ...
    def render_prompt(self, handoff: SuggestionHandoff) -> str: ...
```

#### Logic / Algorithm

1. Copy existing suggestion metadata from the idea into the handoff.
2. Copy `suggestion_context` without rewriting its claims or evidence refs.
3. Keep execution fields distinct: `selected_action` is the complete action, `suggested_steps` contains the first action and bounded execution steps, `deliverables` contains artifacts or outcomes, and `acceptance_checks` contains observable checks.
4. Render sections in this order: identity, problem, reasoning, expected change, decision context, current state, scope/context, action, steps/deliverables, verification, dependencies/capabilities, stop conditions, authority, and report.
5. Render tuple fields one item per line and preserve stable field order.

#### Edge Cases & Error Handling

- A missing or malformed context cannot be hidden by rendering; model validation fails before the prompt is returned.
- Empty optional metadata renders as an explicit “none supplied” line where the section is needed for comprehension.
- The authority line remains the fixed not-granted value, regardless of suggestion wording.

### 6.4 Model-facing prompt assets

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/generator.md`, `src/vidbyte_cli/services/suggestions/prompts/critic.md`
**Type:** Modified

#### What it does

Aligns provider-backed generation and review with the structured context contract while keeping model-facing prose in Markdown.

#### Interface / API

The existing `SuggestionPrompts.generator_system()` and `critic_system()` loaders remain unchanged. Their output instructions gain the new required fields and review criteria.

#### Logic / Algorithm

1. Tell the generator to distinguish problem, insight, causal rationale, expected change, and first action.
2. Require explicit scope boundaries, decision points, beneficiaries, affected surfaces, tradeoffs, risks, unknowns, confidence basis, alternatives, reversibility, time sensitivity, and a procedural verification plan.
3. Tell the critic to verify that claims are supported, the causal link is plausible, context is not repetitive, and verification can produce evidence.
4. Preserve the existing instruction that supplied context is data, not an authority grant.

#### Edge Cases & Error Handling

- Missing or unsupported fields are schema errors, not reasons to silently accept a thin candidate.
- Prompts must continue to load from an installed wheel through `importlib.resources`.
- XML section depth remains within the repository lint rule's sentence band.

### 6.5 Verification script and CI packaging check

**File(s):** `scripts/test-suggestion-handoff-context.py`, `scripts/test_suggestions.py`, `scripts/run_ci.py`
**Type:** New and modified

#### What it does

Adds focused offline coverage for the new contract and makes the canonical gate execute it. The wheel check also verifies the changed generator and critic assets are packaged.

#### Interface / API

```python
def main() -> int: ...
```

#### Logic / Algorithm

1. Instantiate the service and handoff builder directly.
2. Run labeled cases for complete context, goal-only context, invalid nested values, maximum bounded values, deterministic mutation, extraction version, and missing prompt assets.
3. Print `PASS` or `FAIL` for each case and a final `X/Y tests passed` line.
4. Return nonzero if any case fails.
5. Add the script to `scripts/run_ci.py` and add both suggestion Markdown paths to `_WHEEL_RUNTIME_PROMPTS`.

#### Edge Cases & Error Handling

- The script uses no credentials, network, live SDK turn, or persistent state.
- Temporary files are removed in `finally` blocks.
- A missing wheel asset fails the packaging gate even if source imports succeed.

---

## 7. Data Model Changes

### 7.1 Suggestion context and handoff

**Change type:** Modified

```python
class SuggestionHandoff(BaseModel):
    handoff_version: Literal[2] = 2
    suggestion_title: str
    suggestion_summary: str
    primary_category: str
    secondary_categories: tuple[str, ...]
    horizon: IdeaHorizon
    relationship: IdeaRelationship
    readiness: IdeaReadiness
    expected_benefit: str
    effort_estimate: str
    review_summary: str
    evidence_refs: tuple[str, ...]
    suggestion_context: SuggestionContext
```

The complete nested model is defined in Section 6.1. The top-level `SCHEMA_VERSION` and result envelope remain 1 because this is a nested handoff contract change, not a new result envelope.

**Migration strategy:** (if applicable)

- Forward migration: new runs emit version-2 handoffs and consumers should branch on `handoff_version`.
- Rollback plan: revert the feature branch; no database or durable state exists. Existing version-1 result files remain readable only by the prior code revision.

---

## 8. API Changes

N/A - this is a local in-memory/file contract change. The existing `suggestions.result` and `suggestions.handoff` envelope kinds remain unchanged.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-handoff-context.md` | Source-of-truth architecture and test plan for the expanded handoff. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add nested context models, attach context to ideas, and define handoff version 2. |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Generate and preserve complete suggestion context. |
| MODIFY | `src/vidbyte_cli/services/suggestions/handoff.py` | Copy metadata/context and render all structured sections deterministically. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/generator.md` | Require the expanded suggestion context from provider-backed generation. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | Review context completeness, causality, tradeoffs, and verification. |
| MODIFY | `scripts/test_suggestions.py` | Update existing handoff assertions for version 2 and complete context. |
| CREATE | `scripts/test-suggestion-handoff-context.py` | Run focused labeled verification cases required by this design. |
| MODIFY | `scripts/run_ci.py` | Run the focused script and verify suggestion prompt files in the wheel. |

---

## 10. Testing Plan

### Unit Tests

- `[Edge Case]` A goal-only service run creates one complete `SuggestionContext` for every returned idea, including explicit assumption/unknown text and no fabricated evidence refs.
- `[Edge Case]` The smallest requested count produces one valid version-2 handoff with all required nested fields.
- `[Edge Case]` Maximum bounded strings and tuple values validate without truncation or type coercion.
- `[Edge Case]` A 4,096-character valid goal remains lossless in `original_goal` while repeated context excerpts and the rendered prompt stay bounded.
- `[Hidden Failure]` Invalid closed-literal values, empty required strings, extra keys, and unsupported nested shapes fail Pydantic validation before rendering.
- `[Hidden Failure]` Handoff extraction rejects a version-1 nested handoff instead of silently accepting it as version 2.
- `[Silent Failure]` Every existing idea metadata field appears in the handoff with the same value.
- `[Silent Failure]` Every new context value appears under the correct deterministic prompt section.
- `[Silent Failure]` `selected_action`, `suggested_steps`, `deliverables`, and `acceptance_checks` remain distinct rather than reusing one field for multiple meanings.
- `[Silent Failure]` Every verification check carries a claim, procedure, pass condition, evidence target, and failure response.
- `[Silent Failure]` Scope and decision points render with the suggestion context and do not silently become execution authority.
- `[Silent Failure]` Mutating one context field changes the rendered prompt and does not change unrelated fields.
- `[Hidden Assumption]` A suggestion with no evidence refs remains valid and reports an explicit caller-context limitation.
- `[Hidden Assumption]` A suggestion with multiple evidence refs preserves all refs and does not render paths without accompanying summaries.
- `[Hidden Assumption]` A suggestion containing “not granted” language cannot change the fixed authority value.

### Integration Tests

- `[Edge Case]` `agents suggest run --json` returns a result envelope whose ideas contain handoff version 2 and the expanded context.
- `[Hidden Failure]` `agents suggest handoff` extracts a generated version-2 handoff without a model call or credentials.
- `[Silent Failure]` The rendered handoff prompt and JSON handoff agree after a field mutation and re-render.
- `[Hidden Assumption]` A clean wheel contains both suggestion prompt assets and can load them through the installed package.

### Manual / QA Test Cases

1. `[Edge Case]` Run a goal-only suggestion request and confirm the human output remains readable while JSON contains the full context.
2. `[Silent Failure]` Save a result, extract one handoff, and compare its title, rationale, evidence refs, and version with the source idea.
3. `[Hidden Failure]` Edit a saved result to add an unsupported handoff version and confirm extraction fails without stdout data.
4. `[Hidden Assumption]` Run categories, dry-run, and `--help` without provider credentials; confirm all still work.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Pydantic | Existing `>=2.6,<3` | Frozen nested contract validation. | Schema changes are breaking for consumers that require handoff version 1. |
| Existing prompt loader | Local `importlib.resources` loader | Loads generator and critic Markdown from source or wheel. | Missing package data would fail only after installation unless explicitly checked. |
| Existing SDK adapter | Existing optional Vidbyte SDK integration | Consumes the expanded schema when provider-backed generation is enabled. | Provider output may omit fields and must fail schema validation rather than degrade silently. |

---

## 12. Rollout & Deployment

- No feature flag or deployment ordering is needed; this is a local CLI change.
- New output emits handoff version 2. Callers that persist or consume handoffs must inspect the nested version and regenerate packets when needed.
- Rollback is a code revert to the prior branch. No migration or durable data rewrite is required.
- Verification order is focused script, canonical `python scripts/run_ci.py`, then installed-wheel prompt inspection already included in the gate.

---

## 13. Open Questions

- [ ] Should a future release provide an explicit v1-to-v2 handoff migration command for saved result files?
- [ ] Should provider-backed runs enforce a maximum number of risk, tradeoff, and unknown records different from the deterministic template limits?
- [ ] Should the top-level result envelope eventually move to schema version 2 when more nested contracts change?

---

## 14. Alternatives Considered

### Alternative 1: Add only three flat fields

- What: Add `problem_statement`, `proposed_action`, and `verification_plan` directly to the handoff.
- Why rejected: This improves execution clarity but still drops the suggestion's existing metadata and does not preserve the reasoning, uncertainty, tradeoffs, or affected surfaces the caller asked to retain.

### Alternative 2: Put all suggestion context into one narrative string

- What: Add one long `suggestion_context` string and leave the schema otherwise unchanged.
- Why rejected: Agents could not reliably validate, render, or act on individual claims, and structured consumers would need to parse prose.

### Alternative 3: Add every field only to `SuggestionHandoff`

- What: Let the builder invent the expanded context after selection.
- Why rejected: The handoff would not be traceable to the reviewed idea, and the deterministic builder would have to reconstruct reasoning that should be produced and critiqued with the candidate.

### Alternative 4: Bump the entire result envelope to version 2

- What: Change `SCHEMA_VERSION` and both result/handoff payloads together.
- Why rejected: The top-level result envelope is unchanged; versioning only the nested handoff limits the compatibility surface and clearly identifies the breaking contract.
