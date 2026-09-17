# Design Doc: General Suggestion Critic Rubric

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-17

---

## 1. Overview

Add a category-neutral quality rubric to the specialized suggestion critic. The rubric will
evaluate every candidate as a next-action suggestion across ten general sections: current-state
grounding, goal contribution, next-action appropriateness, action definition, problem-action fit,
constraint compliance, distinctness, communication and handoff quality, internal coherence, and
suggestion substance. The rubric lives inside `critic.md` itself. Each section carries a six-to-
eight-sentence explanation of its pillar and nothing else, followed by rating guidelines: six coarse
score bands from 95-100 down to 0-24, each described in three to four sentences that say what a
candidate at that band looks like for that pillar. The critic returns a typed, section-by-section
assessment of coarse scores, and the existing revision packet carries that assessment to the
generator so revisions can target the lowest-scoring sections rather than only a free-form verdict.

---

## 2. Goals & Non-Goals

### Goals

- Add the rubric to `critic.md` so one file carries the critic's whole standing contract.
- Define the ten general suggestion-quality sections requested for every category.
- Give every section a pillar explanation and rating guidelines of coarse score bands.
- Require the critic to return one score, explanation, and evidence-reference list per section.
- Preserve the existing keep/revise/reject, evidence, constraint, duplicate, and repair controls.
- Carry the typed rubric assessment through the existing critic-to-generator revision packet.
- Keep the rubric category-neutral so category-specific overlays can be added later.
- Verify the new prompt is included in the built wheel and the existing offline gate remains green.

### Non-Goals

- Do not add category-specific rubric criteria in this change.
- Do not add effort, cost, risk, impact, reversibility, or economic ranking criteria.
- Do not calculate an aggregate rubric score or replace the existing verdict policy.
- Do not change candidate generation, category registration, selection, or handoff semantics.
- Do not add a new test file; existing offline verification remains the required check.
- Do not expose a new CLI option or API endpoint.

---

## 3. Background & Context

- The suggestion agent already has separate generator, critic, and revision prompts under
  `src/vidbyte_cli/services/suggestions/prompts/`.
- The critic currently returns a verdict, confidence, evidence state, constraint state, duplicate
  reference, repair instruction, preserved fields, and review summary, but no structured rubric
  profile.
- `SuggestionService._revise` serializes complete `SuggestionCritique` models into the revision
  prompt, so adding a nested rubric assessment makes the critic's reasoning available to the
  generator without a new agent call or transport path.
- Prompt assets are loaded through `SuggestionPrompts` and are packaged through the existing
  setuptools Markdown globs; the wheel gate must list the new asset explicitly because import and
  help smoke tests do not read it.
- The general rubric is intentionally separate from category prompts. Category-specific criteria
  can later be layered onto the general assessment without changing this contract.
- The repository requires model-facing prose to live in Markdown prompt assets and requires the
  canonical `python scripts/run_ci.py` gate after source changes.

---

## 4. Requirements

### Functional Requirements

1. The rubric is a section of `critic.md`, so every critic turn carries it without a second asset.
2. The rubric has exactly ten general sections: current-state grounding, goal contribution,
   next-action appropriateness, action definition, problem-action fit, constraint compliance,
   distinctness and non-redundancy, communication and handoff quality, internal coherence, and
   suggestion substance.
3. Every rubric section contains a six-to-eight-sentence explanation of its pillar and a
   `Rating guidelines` list of six score bands, each described in three to four sentences.
4. The rubric instructs the critic to judge only the candidate and supplied context, separate
   candidate defects from missing context, and avoid inventing facts or replacement ideas.
5. `SuggestionCritique` includes a required typed rubric assessment with one entry for each of the
   ten sections.
6. Each rubric assessment entry contains a score from 0 to 100 taken from that section's rating
   guidelines, a concise explanation, and zero or more supporting context references.
7. The critic prompt requires all ten rubric entries for every candidate, in addition to the
   existing control fields.
8. The existing revision packet includes the rubric assessment because it serializes the complete
   critique artifact; the revision prompt explicitly instructs the generator to use the assessment
   when applying a targeted repair.
9. Existing hard controls continue to determine loop behavior; rubric scores diagnose and direct
   repair and are never averaged into one number.
10. The rubric closes with assessment guidelines describing how to work through the pillars, and
    states no output shape, which `critic.md` already owns.
11. `critic.md` stays in the wheel verification list and carries the rubric bytes with it.

### Non-Functional Requirements

- Keep all authored model-facing prose in Markdown; no new model instructions belong in Python.
- Keep prompt loading wheel-safe and preserve the current literal-placeholder behavior.
- Keep the nested assessment bounded so a multi-candidate revision packet remains usable.
- Preserve frozen Pydantic models and `extra="forbid"` validation at the provider boundary.
- Preserve deterministic JSON serialization and stable field names for generator revisions.
- Do not weaken existing lint, formatting, typing, packaging, or offline verification gates.

---

## 5. High-Level Design

The critic system prompt remains the workflow and control contract, and the rubric sits inside it
after the XML control sections. `SuggestionPrompts.critic_system` therefore stays a single read of
`critic.md`, so the critic's standing instructions and its evaluation standard are reviewed, cached,
and shipped as one unit.

The Pydantic model layer will add one bounded assessment-item model carrying a coarse 0-100 score,
and a ten-field `SuggestionCritiqueRubric` model. `SuggestionCritique` will require this nested
model alongside its existing verdict, signal, issue, and repair fields. The service already carries
complete critique models into the revision window, so the rubric automatically travels to the
generator; the revision prompt names that field and tells the generator to repair the lowest-scoring
sections.

```text
[critic.md, rubric included]
                |
        independent critic
                |
 [SuggestionCritique.rubric + controls]
                |
  existing JSON revision packet
                |
          generator revision
```

The rubric is diagnostic rather than a scalar reward. Constraint conflicts and contradictory
evidence remain hard controls, while section scores explain why a candidate should be kept, revised,
or rejected and identify the smallest useful repair.

---

## 6. Detailed Design

### 6.1 General Critic Rubric Section

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/critic.md`
**Type:** Modified

#### What it does

Defines the category-neutral standard for judging whether a candidate is a useful, contextually
appropriate next-action suggestion, inside the same file that already carries the critic's control
contract. The opening paragraph introduces what the rubric is for without naming a rating scale or
an output shape. Each of the ten sections then explains its pillar and supplies rating guidelines,
and a closing `Assessment guidelines` section describes how to work through them.

#### Interface / API

```text
SuggestionPrompts.critic_system() -> str
```

The returned system prompt is `critic.md` in full, rubric included.

#### Logic / Algorithm

1. Introduce the rubric as the standard for grading the generator's ideas, with no rating or output
   vocabulary in the introduction.
2. Present the ten sections in stable order after the XML control sections.
3. Explain each section's pillar in six to eight sentences and nothing else.
4. Follow each explanation with `Rating guidelines`: six score bands from 95-100 to 0-24, each
   described in three to four sentences for that pillar.
5. Close with `Assessment guidelines` covering how to work through the pillars, in six to eight
   sentences that state no output shape.
6. Leave the score, explanation, and evidence-reference contract to the `<Output>` section, which
   already owns what the critic returns.

#### Edge Cases & Error Handling

- Context that cannot answer a section produces a low band with an explanation that says so, never
  an invented higher band.
- A candidate defect is explained against the candidate rather than replaced with a new idea.
- Constraint contradictions remain explicit control signals even when other rubric sections score
  high.
- A category-specific concern is not fabricated by the general rubric; later overlays own it.

### 6.2 Critique Assessment Types

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Adds a typed representation of the critic's section-by-section assessment. The nested structure
keeps ratings, explanations, and evidence references together so the generator receives the exact
diagnosis that led to a revision request. Bounds prevent an individual critique from turning the
revision packet into an unbounded transcript.

#### Interface / API

```python
class SuggestionCritiqueRubricItem(BaseModel):
    score: int
    explanation: str
    evidence_refs: tuple[str, ...]


class SuggestionCritiqueRubric(BaseModel):
    current_state_grounding: SuggestionCritiqueRubricItem
    goal_contribution: SuggestionCritiqueRubricItem
    next_action_appropriateness: SuggestionCritiqueRubricItem
    action_definition: SuggestionCritiqueRubricItem
    problem_action_fit: SuggestionCritiqueRubricItem
    constraint_compliance: SuggestionCritiqueRubricItem
    distinctness_non_redundancy: SuggestionCritiqueRubricItem
    communication_handoff: SuggestionCritiqueRubricItem
    internal_coherence: SuggestionCritiqueRubricItem
    suggestion_substance: SuggestionCritiqueRubricItem
```

`SuggestionCritique` gains `rubric: SuggestionCritiqueRubric` before its existing control fields.

#### Logic / Algorithm

1. Bound every section score to the 0-100 range the rating guidelines are written against.
2. Require a nonempty explanation for every section.
3. Bound explanations and evidence-reference counts with Pydantic fields.
4. Keep models frozen and forbid extra fields like the surrounding suggestion contracts.
5. Preserve the existing validation for revise instructions, constraint quotes, and duplicate IDs.

#### Edge Cases & Error Handling

- A provider response missing any rubric section fails structured-output validation.
- An empty explanation fails validation instead of hiding an omitted review.
- A section the supplied context cannot answer scores in the lowest band and says so.
- The rubric does not override an explicit contradiction or constraint control.

### 6.3 Critic Output Contract

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/library.py`,
`src/vidbyte_cli/services/suggestions/prompts/critic.md`
**Type:** Modified

#### What it does

Updates the critic's output contract to require the ten assessment entries, and keeps the loader a
single read now that the rubric ships inside `critic.md`. The existing critic workflow remains responsible for candidate
identity, evidence checks, duplicates, hard constraints, and verdicts. The rubric supplies the
diagnosis that makes those controls understandable and repairable.

#### Interface / API

```python
def critic_system(self) -> str: ...
```

The method returns `critic.md` unchanged, which now includes the rubric.

#### Logic / Algorithm

1. Read `critic.md` through the existing cache, with no second asset to concatenate.
2. Update the critic output instructions with the exact ten field names.
3. Tell the critic to return the score of the band its rating guidelines place the candidate in.
4. Keep the algorithm pointing at the rubric below rather than at an appended asset.
5. Leave candidate and goal placeholders in the turn prompt unchanged.

#### Edge Cases & Error Handling

- A missing packaged critic prompt raises the same resource error as any missing existing prompt.
- The critic prompt is cached once per `SuggestionPrompts` instance.
- No rubric prose is embedded in Python.
- The critic remains independently usable when category prompts are empty or unrestricted.

### 6.4 Critic-to-Generator Handoff

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/revision.md`
**Type:** Modified

#### What it does

Makes the rubric assessment an explicit part of the generator's revision contract. The service
already serializes each complete `SuggestionCritique`, so the nested `rubric` field is present in
the `Critiques` JSON passed to the revision turn. The revision prompt will direct the generator to
use section ratings and explanations to make minimal, field-level repairs.

#### Interface / API

```text
Revision prompt input: Critiques JSON containing SuggestionCritique.rubric.
```

#### Logic / Algorithm

1. Match each critique to its exact candidate ID.
2. Read the ten rubric assessments alongside the verdict and fix instruction.
3. Locate the lowest-scoring sections that are relevant to the repair.
4. Apply the smallest repair that addresses the stated rubric defect.
5. Preserve fields named by `preserve` and do not invent evidence.
6. Return only revised candidates with their original IDs.

#### Edge Cases & Error Handling

- The generator must not treat a context gap as permission to invent context.
- A rubric weakness without a repairable fix remains a rejected or omitted candidate.
- A high-scoring section does not authorize changing a preserved field.
- Existing revision count and identifier validation remain unchanged.

### 6.5 Wheel Verification

**File(s):** `scripts/run_ci.py`
**Type:** Modified

#### What it does

Keeps the canonical wheel-content verification list pointed at the assets that actually exist. The
rubric ships inside `critic.md`, which is already on the list, so no entry is added. No new test
file is added; the existing CI script remains the single packaging and verification entry point.

#### Interface / API

```text
_WHEEL_RUNTIME_PROMPTS includes:
vidbyte_cli/services/suggestions/prompts/critic.md
```

#### Logic / Algorithm

1. Leave the suggestion stage prompt paths as they are.
2. Let the existing clean-copy build create the wheel.
3. Let the existing archive check require nonempty critic prompt bytes.
4. Keep all existing prompt and category asset checks intact.

#### Edge Cases & Error Handling

- A source-only prompt passes import smoke but fails the archive check, which is intentional.
- A renamed or misplaced asset fails before clean-wheel installation.
- No baseline or lint allowance is changed to admit a missing asset.

---

## 7. Data Model Changes

### 7.1 SuggestionCritiqueRubricItem

**Change type:** New

```text
score: integer from 0 to 100, placed by the section's rating guidelines
explanation: bounded non-empty string
evidence_refs: bounded tuple of run-local context refs
```

### 7.2 SuggestionCritiqueRubric

**Change type:** New

The ten fixed section fields are listed in Section 6.2. The model is nested under
`SuggestionCritique.rubric` and is returned inside the existing critique artifact.

**Migration strategy:** N/A - suggestion results are run responses and are not persisted by this
repository. The prompt version changes from `suggestions.v2` to `suggestions.v3` to identify the
expanded critic contract.

---

## 8. API Changes

### 8.1 SuggestionCritique structured provider artifact

**Change type:** Modified

**Request:** N/A - the critic turn still receives the same goal, candidate IDs, and managed context.

**Response:** Each critique now includes:

```json
{
  "rubric": {
    "current_state_grounding": {
      "score": 75,
      "explanation": "...",
      "evidence_refs": ["ctx-001"]
    }
  }
}
```

The full response contains all ten rubric fields plus the existing critique controls.

**Error cases:**

| Status | Condition |
|--------|-----------|
| Provider schema failure | A critique omits a rubric section or supplies a score outside 0-100. |
| Provider schema failure | A rubric explanation is empty or exceeds its bound. |
| Existing validation failure | Candidate IDs, duplicate IDs, constraints, or revision instructions violate the current contract. |

No HTTP endpoint changes are involved.

---

## 9. File Change Manifest

Complete list of every file that will be created or modified:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-general-rubric.md` | Record the rubric contract and implementation plan before source changes. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | Carry the ten rubric sections and require structured rubric output alongside existing critique controls. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/library.py` | Keep the critic system prompt a single read of `critic.md`. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/revision.md` | Tell the generator to consume rubric assessments during repair, as a numbered algorithm. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add the scored assessment item and the nested critique rubric. |
| MODIFY | `scripts/test_suggestions.py` | Update the existing offline fake critique to satisfy the required rubric artifact. |
| MODIFY | `lint/rules/c003_markdown_xml_section_depth.py` | Measure an enumerated XML section per numbered step instead of per section. |
| MODIFY | `lint/README.md` | Record C003 in the rule catalogue with its two shapes. |

No new test file will be created.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Pydantic | Existing project dependency | Validate nested critic rubric artifacts. | Larger structured output increases provider response size. |
| `importlib.resources` | Python standard library | Load the packaged rubric from source or wheel. | Missing package data would fail at the first critic turn. |
| Existing Vidbyte SDK Codex integration | Existing pinned dependency | Enforce the critic output schema and drive revision turns. | Providers must return the new required fields. |

No new external service or runtime dependency is introduced.

---

## 11. Rollout & Deployment

- No feature flag is required because the rubric is an additive internal critic contract.
- Deploy the prompt asset, schema, loader, and revision instructions together.
- The result prompt version changes to `suggestions.v3` for run-level observability.
- Roll back by reverting the implementation commit; no persisted data migration is required.
- Keep category-specific rubric overlays out of this rollout and design them separately.

---

## 12. Open Questions

- [ ] Should a future category overlay use the same `SuggestionCritiqueRubricItem` type or add a
  separate optional overlay map?
- [ ] Should final public suggestion results expose the accepted rubric, or should it remain only in
  the critic-to-generator revision path for this first version?
- [ ] Should later policy code require particular general sections to clear a minimum band, or
  should the existing critic verdict remain the only keep/revise/reject control initially?
- [ ] Should the ten rubric sections and the thirteen `SuggestionCritiqueSignals` dimensions be
  reconciled, given that several of them now describe the same property at different granularity?

---

## 13. Alternatives Considered

### Alternative 1: Keep the rubric in a separate packaged `critic_rubric.md`

- What: Ship the ten sections as their own asset and append them to the critic system prompt.
- Why rejected: Review asked for the rubric to live in `critic.md`, and one file keeps the critic's
  standing contract reviewable as a unit, with one loader read and one packaged asset to verify.

### Alternative 2: Return only a free-form rubric summary

- What: Ask the critic to describe rubric strengths and weaknesses in `review_summary`.
- Why rejected: The generator cannot reliably identify which section needs repair, and downstream
  code cannot validate that every section was reviewed.

### Alternative 3: Return one aggregate rubric score

- What: Collapse the ten sections into one numeric or ordinal quality score.
- Why rejected: An important problem could still hide a weak action, and a single score would erase
  the exact repair target the generator needs.

### Alternative 4: Recompute the rubric in the service

- What: Have Python derive ratings from the candidate after the critic responds.
- Why rejected: The service cannot interpret open-ended suggestion quality without duplicating model
  reasoning; it should validate and transport the typed critic assessment instead.

### Alternative 5: Add a separate critic-to-generator agent call

- What: Ask another model to summarize the rubric before revision.
- Why rejected: The existing critique artifact already travels to the generator, so another call adds
  latency, cost, and an unnecessary opportunity for diagnostic drift.
