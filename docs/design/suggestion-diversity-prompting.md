# Design Doc: Suggestion Diversity Prompting

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-18
**Last Updated:** 2026-09-18

---

## 1. Overview

The suggestion agent's generator writes its whole candidate pool in one structured call, and
nothing in its prompt protects that pool from collapsing onto the few answers a model gives by
default. Four recent papers on LLM ideation diversity point to specific, cheap, prompt-level
remedies: map broad directions before generating, use ordinary concrete stakeholder lenses as
sampling cues, draft short titles and revise overlap before elaborating, spread candidates from
likely to less typical responses, and judge individual originality separately from set diversity.
This change applies those principles to `prompts/generator.md` and `prompts/critic.md` only. No
Python, schema, command, or loop behavior changes.

---

## 2. Goals & Non-Goals

### Goals
- Make the generator privately map broad directions and concrete stakeholder lenses before it drafts
  any idea (Anchorless Diversification; Barriers to Diversity).
- Make the generator draft short titles first, spread them from typical to less typical responses,
  and revise overlapping titles before elaborating any (Barriers to Diversity CoT; Verbalized Sampling).
- Add a short population-referential divergence instruction to the generator's purpose (Anchorless
  Diversification `diverge`; IDEAFix short-instruction finding).
- Make the critic record individual originality and slate spread as two separate readings, in
  existing schema fields, without letting either replace quality (IDEAFix; all four papers' caveat
  that diversity is not usefulness).
- Keep every edited section inside lint rule C003's sentence bands.

### Non-Goals
- No change to `revision.md`. Revision repairs one reviewed candidate. It must not broaden it, so
  the diversity work belongs to first generation and to review.
- No new schema field. The papers' verbalized probabilities have no field in `SuggestionDraft`. They
  stay private generation cues, which matches the Verbalized Sampling caveat that they are
  not success probabilities.
- No change to `service.py`, `extra_compute.py`, `selection.py`, the pool multiple, round limits,
  or verdict rules. A true multi-call stratified pipeline is listed in section 14 as a follow-up.
- No change to the ten rubric pillars or their bands, which PR #81 settled.
- No automated diversity metric in the CLI. The papers use embedding metrics this CLI does not have.

---

## 3. Background & Context

### Current state
`SuggestionService._run` asks one generator call for a pool of
`min(requested_count * 2, 40)` candidates. It sends the pool to one critic call, then routes
candidates to keep, revise, or drop. With `--extra-compute`, `ExtraComputeService` instead runs one
generator call per selected category in parallel. Those calls cannot see each other's output.
Either way, each generator call is a *list-level* prompt. Verbalized Sampling proves (Claim C2)
that a list-level prompt collapses to a "bestseller list" of top modes. The generator prompt
already bans cosmetic variants (`<Algorithm>` step 5, `<Prohibitions>`). But it never tells the
model *how* to reach different parts of the idea space. Everything it says about variety is about
removing duplicates after they exist.

The critic already judges distinctness (rubric pillar 7, `signals.distinctness`) and whether an idea
is generic (pillar 10's substitution test). It does not separate two different failures: one
candidate being the default answer, and the slate as a whole crowding one mechanism when no two
candidates are duplicates. It also does not say that originality is not quality.

### Research (full papers read)
| Paper | Evidence | What it implies for this prompt layer |
|---|---|---|
| Ibrahim, Azad, Baten, *Anchorless Diversification for Parallel LLM Ideation* (arXiv 2605.30150, 2026) | 150-output pools from GPT-5.4, Claude Sonnet 4.6, and Gemini 2.5 Pro on stories, alternative uses, and slogans. One planning call proposes 5 broad semantic strata (differing in content, not wording, tone, length, or synonyms; balanced; broad; not naming a specific answer), and generation is split evenly across them. This `strat` method gave the best diversity–quality–compute frontier. The one-line `diverge` instruction ("stand out from other responses that might be generated for this same task") raised diversity and quality proxies at about 1.1× the token cost, and it combines with `strat`. Fixed shared anti-anchors (`repr`) moved outputs away from their examples but spread them across few regions. Quality measures were automatic proxies. | Map directions before generating, with the paper's rules for a good direction. Add a population-referential sentence. Do not rely on avoiding a few named examples. |
| Deng, Brucks, Toubia, *Examining and Addressing Barriers to Diversity in LLM-Generated Ideas* (arXiv 2602.20408, 2026) | GPT-4o, fitness products. Two mechanisms: *fixation* (early ideas constrain later ones) and *knowledge aggregation* (first ideas cluster at the center). Seeding with a different first idea did **not** improve later diversity. Ordinary personas (random Tencent personas) beat "creative entrepreneur" personas: 210 vs 164 combinations, against 206 for humans. Ordinary personas also increased within-session fixation. CoT (short titles first, then revise so no two are the same, then expand) reduced fixation. Personas plus CoT gave 248 unique combinations vs 83 default and 197 human (830 ideas each). Revising after full sequential ideas helped much less than titles-first. The paper measures diversity, not usefulness. | Use concrete, ordinary stakeholder lenses as sampling cues. Draft titles before elaborating. Revise overlapping titles while they are cheap to change. Do not count on "start from a different idea." |
| Zhang et al., *Verbalized Sampling* (arXiv 2510.01171, ICML 2026) | Typicality bias in preference data sharpens aligned models toward the mode. Asking for k responses *with their probabilities* raised creative-writing diversity 1.6–2.1× over direct prompting, with no loss in factual accuracy (SimpleQA) or safety. Lower probability thresholds tune diversity upward. Plain list prompts help less. | Privately estimate how typical each title is and keep a spread from likely to less typical. Treat that estimate as a generation cue only, never as a success probability, and never write it into a field. |
| Carichon et al., *IDEAFix* (arXiv 2606.00875, 2026) | 25 prompting strategies × 567 briefs × 5 models. Short instructions to go beyond conventional categories beat long method prompts (C-K, SCAMPER, Design Thinking) on novelty and rarity. Surprising attributes raised individual novelty and rarity while *lowering* set diversity. Homogenization across models persisted. Metrics were automatic. | Keep additions short and targeted. Measure individual originality and set diversity separately, because one can rise while the other falls. |

---

## 4. Requirements

### Functional Requirements
1. `generator.md` `<Goal>` includes one population-referential sentence: ideas should stand out
   from what other capable generators would return for the same goal and context, while still meeting every standard in the prompt.
2. `generator.md` `<Algorithm>` has a private step, before any idea is drafted, that maps broad
   directions. Directions differ in mechanism, lever, or which part of the goal moves, never in wording, tone, scope, or category label. Each is broad enough to hold several ideas and names no specific answer.
3. The same step derives ordinary, concrete stakeholder lenses from the goal and context and says
   why archetypes are weaker. It also says why the map comes first, which is fixation.
4. `generator.md` `<Algorithm>` has a private step that drafts short titles independently within
   each direction and lens before elaborating any. It privately estimates how typical each title is. It keeps a spread from likely to less typical, and it revises titles that share a mechanism.
5. That step states that the typicality estimate is a cue, never a success prediction, appears in no
   field, and earns no candidate a place.
6. `generator.md` `<Output>` asks for the returned candidates to be spread across the mapped
   directions unless the evidence supports only one. It also forbids trading a supported familiar
   candidate for an unsupported unusual one.
7. `critic.md` gains a prose `<Diversity>` section. It separates individual originality (recorded in
   `rubric.suggestion_substance`) from slate spread (recorded in `rubric.distinctness_non_redundancy`
   and `signals.distinctness`).
8. `<Diversity>` tells the critic to log slate-level crowding as a `slate_crowding` issue at `note`
   severity on each crowded candidate. It says never to reject a sound candidate for crowding alone.
9. `<Diversity>` states that originality never lifts a candidate past a weak grounding, fit, or
   constraint reading, and that familiarity never sinks a sound one.
10. `<Diversity>` states that self-described boldness and any stated likelihood are not evidence.
11. `critic.md` `<Algorithm>` gains a step, before the rubric step, that settles both readings.
12. Existing steps keep their text and relative order. Only their numbers change.

### Non-Functional Requirements
- **Lint:** `python lint/run.py` exits 0, and C003 reports no finding in either prompt (prose
  sections 6–8 sentences, numbered steps 3–4 sentences).
- **Cost:** `critic.md` is sent twice per critique turn (system prompt plus rendered turn), so its
  addition stays under about 12 sentences. The generator addition is sent once per generator call.
- **Contract safety:** every field, signal, severity, and issue-code shape named in prose exists in
  `types/suggestions.py` (`slate_crowding` matches `^[a-z][a-z0-9_]*$`, and `note` is a
  `CritiqueIssueSeverity`).
- **Placeholders:** `{{goal}}`, `{{count}}`, and `{{candidate_ids}}` are untouched, and no new token is introduced.
- **Reliability:** `scripts/test_suggestions.py` and `python scripts/run_ci.py` stay green.

---

## 5. High-Level Design

Only two Markdown assets change. Both are packaged through the existing
`services/suggestions/prompts/*.md` package-data glob and loaded by `SuggestionPrompts`.

```
generator.md
  <Goal>       + 1 sentence: stand out from other generators' likely answers (diverge)
  <Algorithm>  1 goal boundary · 2 categories · 3 sort context
               4 NEW map directions + ordinary stakeholder lenses     (strat, personas)
               5 NEW titles first, typical→less-typical spread,        (CoT, verbalized sampling)
                     revise overlapping titles before elaboration
               6 (old 4) what must be true · 7 (old 5) hold drafts against each other
               8 (old 6) commit to count
  <Output>     + 1 sentence: spread across directions; never trade supported for unusual

critic.md
  <CriticOutput>
  <Diversity>  NEW: two separate readings → existing fields; slate_crowding note; not quality
  <Algorithm>  1–4 unchanged · 5 NEW settle originality + slate spread · 6–8 (old 5–7)
  rubric       unchanged
```

The papers' single planning call maps onto private deliberation inside the existing generator call.
The Anchorless paper puts planning in a separate call. This change cannot add one without touching
Python, so the direction map lives in the same reasoning pass. The Barriers paper's batch-CoT result
comes from exactly that setting: one call that lists titles, revises them, and then expands them.
Under `--extra-compute`, the parallel per-category calls are the paper's anchorless parallel
setting. There the population-referential sentence is the only cross-call pressure available.

The critic keeps verdict control exactly as it is. Diversity readings are observations, not repair
orders. A revision turn may not introduce a new idea, so asking it to "diversify" would contradict
`revision.md`.

---

## 6. Detailed Design

### 6.1 Generator goal sentence
**File(s):** `src/vidbyte_cli/services/suggestions/prompts/generator.md`
**Type:** Modified

#### What it does
Adds the population-referential divergence instruction at the level of purpose, as the fourth
sentence, right after "Let the supplied context decide…".

#### Interface / API
```
Aim for ideas that would stand out from what other capable generators given this same goal and
context would return, while still meeting every standard this prompt sets.
```

#### Logic / Algorithm
1. Insert the sentence. `<Goal>` goes from 6 to 7 sentences.

#### Edge Cases & Error Handling
- It names no output field, which keeps to the field-guide altitude rule for `<Goal>`.
- "while still meeting every standard" keeps grounding and constraints first.

### 6.2 Generator algorithm steps 4 and 5
**File(s):** `generator.md` `<Algorithm>`
**Type:** Modified

#### Interface / API
Step 4 (directions and lenses) and step 5 (titles, typicality spread, overlap revision), 4
sentences each. The exact text is in the implementation commit.

#### Logic / Algorithm
1. Insert the new step 4 after "Sort every context item…", so directions are drawn only after the
   model knows what is settled and forbidden.
2. Insert the new step 5 after it.
3. Renumber old steps 4–6 to 6–8 without changing their text.

#### Edge Cases & Error Handling
- Thin context: lenses are "positions the goal or context implies". The step does not require them
  to be named in context, but step 6 and `<Prohibitions>` still require any fact about them to be an
  assumption.
- Single category under `--extra-compute`: directions are mapped within that category's space. The
  step speaks of "the goal's space of useful next actions", not the category taxonomy.
- Probability leaking into fields: step 5 states that the estimate "appears in no field".

### 6.3 Generator output sentence
**File(s):** `generator.md` `<Output>`
**Type:** Modified

```
Spread the returned candidates across the directions you mapped rather than letting one direction
fill most of the slate unless the evidence supports only that one, and never trade a supported
familiar candidate for an unusual one the evidence cannot carry.
```
`<Output>` goes from 7 to 8 sentences.

### 6.4 Critic `<Diversity>` section
**File(s):** `src/vidbyte_cli/services/suggestions/prompts/critic.md`
**Type:** Modified (new section between `<CriticOutput>` and `<Algorithm>`)

#### What it does
Seven prose sentences. They separate the two readings, route each one to an existing field, define
the `slate_crowding` note, forbid treating originality as quality, and discount self-described
boldness and stated likelihoods.

#### Edge Cases & Error Handling
- A slate of one candidate: slate spread is not meaningful. The distinctness signal's own
  description already allows `unknown` when the rest of the batch is not visible.
- Every candidate crowded: each gets a `note`, none is rejected for crowding, and true duplicates
  still go through `duplicate_of` under step 4.
- Issue-list cap (12): one `slate_crowding` issue per candidate at most.

### 6.5 Critic algorithm step 5
**File(s):** `critic.md` `<Algorithm>`
**Type:** Modified

A new 4-sentence step 5, placed after the duplicate step and before "Apply every section of the
general suggestion rubric". It explains why crowding cannot be seen in pairwise comparison and
why both readings are settled before the rubric. Old steps 5–7 become 6–8 with their text unchanged.

---

## 7. Data Model Changes

N/A. Every reading is recorded in fields that already exist (`rubric.suggestion_substance`,
`rubric.distinctness_non_redundancy`, `signals.distinctness`, `issues[]`).

---

## 8. API Changes

N/A. No command, option, or HTTP surface changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-diversity-prompting.md` | This design doc |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/generator.md` | Goal sentence, algorithm steps 4–5, output sentence |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | `<Diversity>` section, algorithm step 5 |
| CREATE | `scripts/test-suggestion-diversity-prompting.py` | Verification script for section 10 |
| MODIFY | `scripts/run_ci.py` | Run that script as a source gate, so the checks are enforced rather than decorative |

---

## 10. Testing Plan

### Unit Tests
- `describe('generator prompt')` → `it('orders directions, titles, then what-must-be-true')`. Step 4
  mentions directions, step 5 titles, step 6 "what would have to be true" — [Hidden Assumption]
- `describe('generator prompt')` → `it('has exactly eight numbered algorithm steps numbered 1..8')` — [Edge Case]
- `describe('generator prompt')` → `it('keeps every pre-existing step sentence verbatim')` — [Silent Failure]
- `describe('generator prompt')` → `it('states the typicality estimate appears in no field')` — [Silent Failure]
- `describe('generator prompt')` → `it('prohibitions keep eight bullets unchanged')` — [Silent Failure]
- `describe('generator prompt')` → `it('renders goal and count with no new unreplaced token')` — [Hidden Failure]
- `describe('critic prompt')` → `it('has a Diversity section between CriticOutput and Algorithm')` — [Edge Case]
- `describe('critic prompt')` → `it('names only rubric/signal fields that exist in the schema')` — [Hidden Assumption]
- `describe('critic prompt')` → `it('slate_crowding matches the issue-code pattern and note is a severity')` — [Hidden Assumption]
- `describe('critic prompt')` → `it('a critique carrying a slate_crowding note validates against SuggestionCritique')` — [Hidden Failure]
- `describe('critic prompt')` → `it('keeps ten rubric sections with ten Rating guidelines')` — [Silent Failure]
- `describe('critic prompt')` → `it('algorithm step 5 precedes the rubric step')` — [Hidden Assumption]
- `describe('both prompts')` → `it('pass C003 with zero findings')` — [Edge Case]
- `describe('both prompts')` → `it('contain no angle-bracket text inside sections that C003 would parse as tags')` — [Hidden Failure]
- `describe('schema')` → `it('SuggestionDraft still forbids a probability field')` — [Hidden Assumption]

### Integration Tests
- `python scripts/test_suggestions.py`: the full offline loop through the SDK fake still passes, including
  "generator critic and revision prompts are distinct and loaded".
- A silent failure path between the components: a new sentence could accidentally include a `{{…}}` token
  that `_render` never fills, and the model would see it literally. This is covered by the render test.
- `python scripts/run_ci.py`: lint, types, tests, wheel build, and clean-install smoke.

### Manual / QA Test Cases
1. Given a goal with one obvious answer, when the agent runs, then the returned candidates span more
   than one mechanism and no candidate says "bold" or a percentage in its title — [Silent Failure]
2. Given `--extra-compute` with two categories, when it runs, then each category's candidates still
   come from several directions inside that category — [Edge Case]
3. Given a slate where every candidate uses the same lever, when critiqued, then each carries a
   `slate_crowding` note and none is rejected only for that — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None new | — | Prompt text only | Model behavior change is not measured offline |

---

## 12. Rollout & Deployment

- No feature flag. The prompt change applies to every run once released.
- Not breaking. The output schemas are unchanged.
- Rollback: revert the two Markdown files.

---

## 13. Open Questions

- [ ] Open PRs #80 and #83 rewrite `critic.md` from an older shape that has no rubric. Whichever
      lands second must carry `<Diversity>` and step 5 forward, or drop them on purpose.
- [ ] Should `prompt_version` (`suggestions.v3`) be bumped for a prompt-only behavior change? It is
      left unchanged here because earlier prompt PRs (#79, #81) did not bump it.
- [ ] Should a follow-up add a real planning call that allocates the pool across directions (the
      paper's `strat`)? That needs Python and a schema.

---

## 14. Alternatives Considered

### Alternative 1: Add a `probability` field to `SuggestionDraft`
- What: literal Verbalized Sampling, with a stated probability on every candidate.
- Why rejected: out of the prompt-only scope. It also risks readers treating the number as a chance
  of success, which the research summary explicitly warns against.

### Alternative 2: A long creativity framework section (SCAMPER / TRIZ / design thinking)
- What: a large new `<Creativity>` section in the generator.
- Why rejected: IDEAFix found that long method prompts did not beat short targeted instructions on
  novelty. It would also exceed C003's band and add cost on every call.

### Alternative 3: A separate planning call that stratifies the pool
- What: the Anchorless `strat` pipeline, with one call proposing directions and N calls each
  generating inside one.
- Why rejected here: it changes `service.py` and `extra_compute.py`. It is recorded as a follow-up.

### Alternative 4: Critic requests revisions that diversify the slate
- What: a revise verdict for crowding.
- Why rejected: `revision.md` forbids introducing a new idea or broadening scope. The Anchorless
  paper also found that representative anti-anchoring spreads outputs poorly.
