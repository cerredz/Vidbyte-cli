# Design Doc: Critic Stakeholder Lenses

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-18
**Last Updated:** 2026-09-18

---

## 1. Overview

The suggestion critic scores every candidate against a ten-pillar general rubric that lives in
`services/suggestions/prompts/critic.md`. Every pillar reads the candidate from one seat: the
caller's. This change adds an eleventh pillar, **Stakeholder perspectives**, that tells the critic
to use concrete stakeholder lenses. The critic looks at each candidate from the positions of the
people it would touch: people with different jobs, resources, incentives, or constraints who
are relevant to the caller's role and goal. It then scores how well the candidate holds up from
those positions. The pillar says plainly that these simulated perspectives help search but do not
substitute for customer evidence. Its score is returned in the same shape as the other ten: a
coarse band, an explanation that names the lenses applied, and existing evidence references.

---

## 2. Goals & Non-Goals

### Goals
- Add a Stakeholder perspectives pillar to the critic's general rubric, written in the same form as
  the existing ten (a 6–8 sentence explanation followed by 5–6 rating bands of 3–4 sentences).
- Tell the critic to reason through lenses relevant to the caller's role and goal, inside its own
  single review turn.
- State the evidence boundary: a lens can raise a question or expose a gap, but it never counts as
  support for a claim and never lifts `evidence_check`.
- Return the pillar's reading in the structured critique as `rubric.stakeholder_perspectives`, like
  every other pillar, with the lenses named in its explanation.
- Keep the prompt, the `<Output>` contract, the schema, and the revision prompt in agreement about
  the rubric's section count (ten → eleven).

### Non-Goals
- No personas, no extra agents, no extra model turns, and no parallel critic instances. The critic
  imagines the lenses inside the one turn it already takes.
- No change to the verdict controls. Keep/revise/reject remain the only loop control signals, and
  the new score is not averaged with other scores or used for selection.
- No change to the generator prompt or to category assets.
- No new CLI option, and no caller-supplied stakeholder list.

---

## 3. Background & Context

- The ten-pillar rubric landed in PR #81 (`docs/design/suggestion-general-rubric.md`). Every pillar
  asks whether the candidate is right *for the caller*. None asks who else the action lands on:
  the executor, the approver, the payer, the end user, or whoever inherits the consequences.
- A candidate can score well on all ten pillars and still fail on contact with a person it
  silently depends on. This happens when it moves work onto someone with no capacity for it,
  assumes an approval, or delivers a benefit its intended user would not value.
- The user asked for the idea in these words: *"Use concrete stakeholder lenses. Explore the
  situation from people with different jobs, resources, incentives, or constraints. These
  simulated perspectives help search; they do not substitute for customer evidence."* They
  explicitly ruled out creating personas or running multiple instances.
- Constraint from the field guide (`agent-stage-prompts.md`, "A rubric a stage reads lives in that
  stage's prompt…"): the rubric lives in `critic.md`, its sections carry no output vocabulary, the
  output contract stays in `<Output>`, and its bands must be expressible in the schema.
- Overlap: open PR #80 (`feat/suggestion-general-critic-context`, currently CONFLICTING) also edits
  `critic.md`. This change targets `main`. Whichever PR merges second will need a small rebase in
  `<Algorithm>`/`<Output>`.

---

## 4. Requirements

### Functional Requirements
1. `critic.md` contains a rubric section `## 11. Stakeholder perspectives` placed after
   `## 10. Suggestion substance` and before `## Assessment guidelines`.
2. The section explanation directs the critic to take concrete stakeholder lenses: people who
   differ in job, resources, incentives, or constraints and who are relevant to the caller's role
   and goal.
3. The section explanation states that simulated perspectives help the search and do not
   substitute for customer evidence. A lens never counts as support for a claim.
4. The section explanation says the lenses are applied within the critic's own review, and that
   stakeholder positions stated in the supplied context outrank imagined ones.
5. The section has a `### Rating guidelines` block with six bands on the same 0–100 scale as the
   other pillars.
6. `<Output>` lists `stakeholder_perspectives` among the required rubric keys and tells the critic
   to name the lenses applied, and what each surfaced, in that section's explanation.
7. Every count of rubric sections in `critic.md` (intro, `<Algorithm>` step 5, `<Output>`) and
   `revision.md` reads eleven.
8. `SuggestionCritiqueRubric` has a required field `stakeholder_perspectives:
   SuggestionCritiqueRubricItem`. Its `Field(description=...)` summarises the pillar and repeats the
   evidence boundary, because that description is what the model sees at the wire boundary.
9. A critique that omits `stakeholder_perspectives` fails validation, just as omitting any other
   pillar does.

### Non-Functional Requirements
- Performance: no extra turns. The prompt grows by roughly 3 KB, and because `critic.md` is sent
  twice per critic turn (system prompt and rendered turn), the total increase is about 6 KB. That
  cost is acceptable and follows the same pattern as the existing pillars.
- Security: no new input surface. The lenses are imagined by the critic and are never executed.
- Observability: the new score appears in JSON/JSONL result critiques automatically, because the
  rubric is already serialised.
- Reliability: a provider response missing the new key is rejected by the existing schema
  validation and surfaces as the existing provider/schema failure. It is never silently defaulted.

---

## 5. High-Level Design

The change is prose plus one schema field. The rubric is a Markdown section of the critic's system
prompt, and the structured critique schema lists one `SuggestionCritiqueRubricItem` per pillar.
Adding a pillar therefore means adding (a) one prose section with rating bands, (b) one required
schema field, and (c) keeping every "ten" in the prompt family consistent.

```
critic.md  ──(system prompt + turn)──►  critic agent (one turn, unchanged)
   └─ ## 11. Stakeholder perspectives        │
                                             ▼
                       SuggestionCritique.rubric.stakeholder_perspectives  (new required key)
                                             │
                                             ▼
               revision.md reads the full (eleven-section) rubric ─► revision turn
```

Key decisions:
- **A pillar, not an `<Algorithm>` step.** The user asked for it "in the rubric". A pillar also gets
  its own score and explanation, which is how the revision turn finds what to repair. An algorithm
  step would produce no traceable output.
- **Required, not optional, field.** Every other pillar is required, and an optional one would let
  the model skip the lens reasoning silently.
- **Lenses named in the explanation, not in a new list field.** This reuses the existing item shape
  (score/explanation/evidence_refs). The user asked for output "like we have", not a new structure.

---

## 6. Detailed Design

### 6.1 Critic prompt rubric

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/critic.md`
**Type:** Modified

#### What it does
Adds the eleventh pillar and updates the section counts and the output contract.

#### Interface / API
New Markdown section (full text is in the implementation):
```
## 11. Stakeholder perspectives
<7-sentence pillar explanation>
### Rating guidelines
- **95-100 — holds from every relevant seat.** …
- **85-94 — …**  - **70-84 — …**  - **50-69 — …**  - **25-49 — …**  - **0-24 — …**
```

#### Logic / Algorithm
1. Intro paragraph: "ten pillars" → "eleven pillars".
2. `<Algorithm>` step 5: "same ten grounds" / "all ten readings" → eleven.
3. `<Output>`: "ten-section" → "eleven-section". Append `stakeholder_perspectives` to the key list,
   and add one sentence telling the critic to name the lenses and what each surfaced in that
   section's explanation, citing only real context references.
4. Insert the pillar after pillar 10.

#### Edge Cases & Error Handling
- The context names no stakeholders: the pillar tells the critic to choose lenses the goal plainly
  implies rather than inventing an audience.
- The context states a stakeholder's position: that stated position outranks the imagined lens.
- A lens suggests a claim is true: the pillar says the lens is not evidence. `evidence_check` still
  follows the supplied context only.

### 6.2 Critique rubric schema

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### Interface / API
```python
stakeholder_perspectives: SuggestionCritiqueRubricItem = Field(description=(...))
```
The class docstring and the `SuggestionCritique.rubric` description change "ten" to "eleven".

#### Edge Cases & Error Handling
- Missing key → pydantic `ValidationError` (the model config already has `extra="forbid"` and the
  field is required). This propagates through the existing provider-failure path.

### 6.3 Revision prompt

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/revision.md`
**Type:** Modified

Step 2: "ten-section" → "eleven-section". No other change.

---

## 7. Data Model Changes

### 7.1 SuggestionCritiqueRubric

**Change type:** Modified

```python
class SuggestionCritiqueRubric(BaseModel):
    ...
    suggestion_substance: SuggestionCritiqueRubricItem
    stakeholder_perspectives: SuggestionCritiqueRubricItem  # new, required
```

**Migration strategy:** N/A. Critiques are transient per-run artifacts and nothing persists or
reloads them, so no stored documents need migrating. Result JSON gains one key, which is additive
for consumers.

---

## 8. API Changes

N/A. No HTTP route or CLI option changes. The only visible change is one extra key under
`critiques[].rubric` in JSON/JSONL output.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/critic-stakeholder-lenses.md` | This design doc |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | New pillar 11, counts, `<Output>` key + lens instruction |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/revision.md` | Section count ten → eleven |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Required `stakeholder_perspectives` rubric field, counts |
| MODIFY | `scripts/test_suggestions.py` | Fake supplies the new key; new checks for prompt/schema agreement |

---

## 10. Testing Plan

The repository's suggestion checks live in `scripts/test_suggestions.py`, which `scripts/run_ci.py`
already runs. New cases are added there rather than in a parallel script, so that CI exercises
them.

### Unit Tests
- `critic prompt carries the stakeholder perspectives pillar with its evidence boundary`: the
  section exists and includes "do not substitute for customer evidence". — [Silent Failure] (the
  pillar could be added without the caveat and still read well)
- `rubric rating-guideline count equals schema section count`: the number of `### Rating guidelines`
  headings equals `len(SuggestionCritiqueRubric.model_fields)`, which is 11. — [Hidden Assumption]
  (prompt and schema are assumed to agree)
- `critic output contract names every rubric schema key`: every schema field name appears in
  `<Output>`. — [Hidden Assumption]
- `no stale "ten-section" count remains in critic or revision prompts`: "ten-section", "ten
  pillars", and "all ten" are absent. — [Silent Failure]
- `rubric missing stakeholder_perspectives is rejected`: building the rubric from the other ten
  items raises `ValidationError`. — [Edge Case]
- `stakeholder perspectives description reaches the wire schema`: `model_json_schema()` contains
  the field with a description that mentions customer evidence. — [Hidden Failure] (the model never
  sees a caveat that exists only in Python)

### Integration Tests
- The existing offline `SuggestionService` run with `FakeSdk` must still pass end to end with the
  fake now returning eleven sections. — [Hidden Failure]
- `revision window carries the complete rubric assessment` is extended to require
  `stakeholder_perspectives` in the revision context text. — [Silent Failure] (a dropped key would
  starve the revision turn)

### Manual / QA Test Cases
1. Given a configured provider, when `vidbyte-cli --json agents suggest run --goal "…"` runs, then
   every critique's `rubric` has `stakeholder_perspectives` whose explanation names concrete lenses.
   — [Hidden Assumption]
2. Given a goal whose context names no stakeholders, the explanation uses lenses the goal implies
   and does not claim what a stakeholder "said". — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| pydantic | existing pin | Schema validation | None new |
| Suggestion provider (via vidbyte-sdk) | existing | Structured critic output | A provider may occasionally omit the new key and trigger the existing schema-failure path |

---

## 12. Rollout & Deployment

- No feature flag. The change is prompt text plus an additive result key.
- Not a breaking change for CLI callers. It is breaking for any code that constructs
  `SuggestionCritiqueRubric` directly (only the test fake does).
- Rollback: revert the commit.

---

## 13. Open Questions

- [ ] Should the pillar's score ever inform verdicts (for example, a 0–24 band forcing a revise)?
      This design keeps it descriptive, like the other pillars.
- [ ] PR #80 also edits `critic.md`. Whichever merges second rebases the count/key edits.

---

## 14. Alternatives Considered

### Alternative 1: Multiple persona critics
- What: run one critic per stakeholder persona and merge the results.
- Why rejected: the user explicitly ruled it out, and it multiplies cost and turns.

### Alternative 2: An `<Algorithm>` step only
- What: add a "consider stakeholders" step to the critic's private reasoning.
- Why rejected: it produces no scored, traceable output, and the user asked for it in the rubric.

### Alternative 3: A new `lenses: list[...]` field
- What: a structured list of lenses with a finding for each.
- Why rejected: this is a new output shape where the user asked for the existing one, and the
  item's explanation already carries it.
