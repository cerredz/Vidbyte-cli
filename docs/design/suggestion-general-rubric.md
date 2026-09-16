# Design Doc: General Suggestion Critic Rubric

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

Add a category-neutral quality rubric to the specialized suggestion critic. The rubric will
evaluate every candidate as a next-action suggestion across ten general sections: current-state
grounding, goal contribution, next-action appropriateness, action definition, problem-action fit,
constraint compliance, distinctness, communication and handoff quality, internal coherence, and
suggestion substance. Each section will carry a four-to-five-sentence description, concrete things
to consider, and questions for the critic to ask itself. The critic will return a typed,
section-by-section assessment, and the existing revision packet will carry that assessment to the
generator so revisions can target the rubric weaknesses rather than only a free-form verdict.

---

## 2. Goals & Non-Goals

### Goals

- Add one packaged Markdown rubric asset attached to the critic system prompt.
- Define the ten general suggestion-quality sections requested for every category.
- Give every section a description, consideration bullets, and self-review questions.
- Require the critic to return one rating, explanation, and evidence-reference list per section.
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

1. `critic_rubric.md` is loaded and appended to the critic's system prompt for every critic turn.
2. The rubric has exactly ten general sections: current-state grounding, goal contribution,
   next-action appropriateness, action definition, problem-action fit, constraint compliance,
   distinctness and non-redundancy, communication and handoff quality, internal coherence, and
   suggestion substance.
3. Every rubric section contains a four-to-five-sentence description, a bullet list of things to
   consider, and a bullet list of questions for the critic to ask itself.
4. The rubric instructs the critic to judge only the candidate and supplied context, separate
   candidate defects from missing context, and avoid inventing facts or replacement ideas.
5. `SuggestionCritique` includes a required typed rubric assessment with one entry for each of the
   ten sections.
6. Each rubric assessment entry contains a rating (`strong`, `adequate`, `weak`, or `unknown`), a
   concise explanation, and zero or more supporting context references.
7. The critic prompt requires all ten rubric entries for every candidate, in addition to the
   existing control fields.
8. The existing revision packet includes the rubric assessment because it serializes the complete
   critique artifact; the revision prompt explicitly instructs the generator to use the assessment
   when applying a targeted repair.
9. Existing hard controls continue to determine loop behavior; rubric ratings diagnose and direct
   repair but do not become an aggregate score.
10. The new Markdown asset is included in the wheel verification list and can be read through
    `SuggestionPrompts` after installation.

### Non-Functional Requirements

- Keep all authored model-facing prose in Markdown; no new model instructions belong in Python.
- Keep prompt loading wheel-safe and preserve the current literal-placeholder behavior.
- Keep the nested assessment bounded so a multi-candidate revision packet remains usable.
- Preserve frozen Pydantic models and `extra="forbid"` validation at the provider boundary.
- Preserve deterministic JSON serialization and stable field names for generator revisions.
- Do not weaken existing lint, formatting, typing, packaging, or offline verification gates.

---

## 5. High-Level Design

The critic system prompt remains the workflow and control contract. `SuggestionPrompts.critic_system`
will append the new packaged `critic_rubric.md` contents after the existing critic prompt, giving the
critic one stable general evaluation standard without duplicating the prose in Python or in every
turn prompt.

The Pydantic model layer will add a reusable rubric-rating enum, one bounded assessment-item model,
and a ten-field `SuggestionCritiqueRubric` model. `SuggestionCritique` will require this nested
model alongside its existing verdict and repair fields. The service already serializes complete
critique models into `revision_turn`, so the rubric automatically travels to the generator; the
revision prompt will name that field and tell the generator to repair the weak or unknown sections.

```text
[critic.md + critic_rubric.md]
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
evidence remain hard controls, while ratings explain why a candidate should be kept, revised, or
rejected and identify the smallest useful repair.

---

## 6. Detailed Design

### 6.1 General Critic Rubric Asset

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/critic_rubric.md`
**Type:** New file

#### What it does

Defines the category-neutral standard for judging whether a candidate is a useful, contextually
appropriate next-action suggestion. Each section contains the requested description, consideration
bullets, and self-review questions. The asset also defines shared ratings and output discipline so
the critic's assessment is consistent across all suggestion categories.

#### Interface / API

```text
SuggestionPrompts.critic_system() -> str
```

The returned system prompt consists of the existing critic prompt followed by the rubric asset.

#### Logic / Algorithm

1. State the general review rules before the section-by-section rubric.
2. Present the ten sections in stable order.
3. Give each section four-to-five descriptive sentences.
4. Follow each description with `Things to consider` and `Questions to ask yourself` bullets.
5. Require one rating, explanation, and evidence-reference list for every section.
6. Instruct the critic to keep ratings independent and use existing verdict controls for action.

#### Edge Cases & Error Handling

- A missing fact is `unknown`, not an invented `adequate` rating.
- A candidate defect is explained against the candidate rather than replaced with a new idea.
- Constraint contradictions remain explicit control signals even when other rubric sections are
  strong.
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
class CritiqueRubricRating(StrEnum): ...


class SuggestionCritiqueRubricItem(BaseModel):
    rating: CritiqueRubricRating
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

1. Use one enum for all section ratings: `strong`, `adequate`, `weak`, and `unknown`.
2. Require a nonempty explanation for every section.
3. Bound explanations and evidence-reference counts with Pydantic fields.
4. Keep models frozen and forbid extra fields like the surrounding suggestion contracts.
5. Preserve the existing validation for revise instructions, constraint quotes, and duplicate IDs.

#### Edge Cases & Error Handling

- A provider response missing any rubric section fails structured-output validation.
- An empty explanation fails validation instead of hiding an omitted review.
- Unknown ratings remain valid when the supplied context cannot answer a question.
- The rubric does not override an explicit contradiction or constraint control.

### 6.3 Critic Prompt Attachment

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/library.py`,
`src/vidbyte_cli/services/suggestions/prompts/critic.md`
**Type:** Modified

#### What it does

Loads the rubric as part of the critic system prompt and updates the critic's output contract to
require the ten assessment entries. The existing critic workflow remains responsible for candidate
identity, evidence checks, duplicates, hard constraints, and verdicts. The rubric supplies the
diagnosis that makes those controls understandable and repairable.

#### Interface / API

```python
def critic_system(self) -> str: ...
```

The method returns the existing critic prompt plus the trimmed rubric asset separated by a blank
line.

#### Logic / Algorithm

1. Read `critic.md` through the existing cache.
2. Read `critic_rubric.md` through the same wheel-safe resource loader.
3. Concatenate them in that order.
4. Update the critic output instructions with the exact ten field names and rating vocabulary.
5. Leave candidate and goal placeholders in the turn prompt unchanged.

#### Edge Cases & Error Handling

- A missing packaged rubric raises the same resource error as any missing existing prompt.
- The rubric is cached once per `SuggestionPrompts` instance.
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
3. Locate weak or unknown sections that are relevant to the repair.
4. Apply the smallest repair that addresses the stated rubric defect.
5. Preserve fields named by `preserve` and do not invent evidence.
6. Return only revised candidates with their original IDs.

#### Edge Cases & Error Handling

- The generator must not treat `unknown` as permission to invent context.
- A rubric weakness without a repairable fix remains a rejected or omitted candidate.
- A strong section does not authorize changing a preserved field.
- Existing revision count and identifier validation remain unchanged.

### 6.5 Wheel Verification

**File(s):** `scripts/run_ci.py`
**Type:** Modified

#### What it does

Adds the rubric asset to the canonical wheel-content verification list. This ensures the installed
package contains the prompt that the critic system loader will request. No new test file is added;
the existing CI script remains the single packaging and verification entry point.

#### Interface / API

```text
_WHEEL_RUNTIME_PROMPTS includes:
vidbyte_cli/services/suggestions/prompts/critic_rubric.md
```

#### Logic / Algorithm

1. Add the exact wheel-relative path next to the other suggestion stage prompts.
2. Let the existing clean-copy build create the wheel.
3. Let the existing archive check require nonempty rubric bytes.
4. Keep all existing prompt and category asset checks intact.

#### Edge Cases & Error Handling

- A source-only prompt passes import smoke but fails the archive check, which is intentional.
- A renamed or misplaced asset fails before clean-wheel installation.
- No baseline or lint allowance is changed to admit a missing asset.

---

## 7. Data Model Changes

### 7.1 Critique Rubric Rating

**Change type:** New

```text
CritiqueRubricRating = strong | adequate | weak | unknown
```

### 7.2 SuggestionCritiqueRubricItem

**Change type:** New

```text
rating: CritiqueRubricRating
explanation: bounded non-empty string
evidence_refs: bounded tuple of run-local context refs
```

### 7.3 SuggestionCritiqueRubric

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
      "rating": "adequate",
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
| Provider schema failure | A critique omits a rubric section or supplies an invalid rating. |
| Provider schema failure | A rubric explanation is empty or exceeds its bound. |
| Existing validation failure | Candidate IDs, duplicate IDs, constraints, or revision instructions violate the current contract. |

No HTTP endpoint changes are involved.

---

## 9. File Change Manifest

Complete list of every file that will be created or modified:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-general-rubric.md` | Record the rubric contract and implementation plan before source changes. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/critic_rubric.md` | Define the ten general rubric sections and review instructions. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | Require structured rubric output alongside existing critique controls. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/library.py` | Append the packaged rubric to the critic system prompt. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/revision.md` | Tell the generator to consume rubric assessments during repair. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add typed rubric ratings, assessment items, and the nested critique rubric. |
| MODIFY | `scripts/run_ci.py` | Verify the new prompt is present in the built wheel. |
| MODIFY | `scripts/test_suggestions.py` | Update the existing offline fake critique to satisfy the required rubric artifact. |

No files will be deleted. No new test file will be created.

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
- [ ] Should later policy code require particular general sections to be at least `adequate`, or
  should the existing critic verdict remain the only keep/revise/reject control initially?

---

## 13. Alternatives Considered

### Alternative 1: Put the full rubric directly in `critic.md`

- What: Add all ten sections to the existing critic system prompt file.
- Why rejected: A separate asset keeps the workflow prompt and reusable evaluation standard
  independently reviewable and makes later category overlays easier to compose.

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
