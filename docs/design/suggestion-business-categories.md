# Design Doc: Suggestion Business Categories

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

Add five focused business lenses to the suggestion agent: customer and market, business model and
monetization, brand and positioning, distribution and sales, and customer relationship and service.
Each lens is a closed registry value backed by a packaged Markdown prompt. The existing broad
business-and-growth category remains available for cross-cutting commercial ideas. This follow-up
also gives every business prompt touched by PR #59 the same generation-oriented structure, so a
selected category does more than describe a lens: it tells the generator how to produce a candidate
whose mechanism, evidence, action, and completion signal stay inside that lens.

---

## 2. Goals & Non-Goals

### Goals

- Add five unique category IDs and one prompt asset per ID.
- Turn the supplied descriptions and questions into the repository's full category prompt shape.
- State boundaries against `business_growth`, `product_experience`, and the new sibling categories.
- Keep category listing, selection, validation, packaging, and agent rendering data-driven.
- Give all six business prompt assets touched by PR #59 the same generation contract:
  `Generation requirements`, `Candidate shape`, `Valid suggestion directions`, and
  `Alignment check`.
- Make each of those sections materially deep enough to guide generation rather than merely label
  the category: approximately twice the earlier 100-200-word guidance targets, with category-
  specific content rather than copied boilerplate.
- Add optional evidence, failure-mode, context-signal, and success-signal guidance where it closes
  a gap that the four required sections do not already cover.

### Non-Goals

- No changes to generation, critique, context, result, or service orchestration.
- No removal or renaming of existing category IDs.
- No market research or factual claims beyond the category guidance itself.
- No requirement that the older 31 non-business category assets adopt this expanded business
  structure in this PR; that would be a separate prompt-taxonomy migration.

---

## 3. Background & Context

The merged suggestion agent currently exposes 31 categories and one Markdown asset for each. Its
`business_growth` and `product_experience` prompts are useful but broad, so commercial requests
about audience, pricing, message, channel, or post-purchase value collapse into one lens. The new
categories make those decisions independently selectable and easier for the generator to vary.

The repository's C004 rule requires every category asset to have one title, a six-to-eight sentence
description, and eight-to-ten considerations. The existing `feat/suggestion-category-prompts`
branch deepens the current 31 assets; this PR preserves that work's structure for the five new
assets and narrows the broad business-growth boundary. The current category files explain when a
lens applies, but the generator prompt only receives those explanations alongside a generic output
contract. That leaves a model free to produce a superficially related idea, such as a slogan under
brand positioning or a new channel under customer and market.

The requested follow-up therefore adds four long, category-specific sections to each of the five
new assets and to the `business_growth` umbrella asset touched by this PR. The repeated headings
make the assets easy to inspect, while the tailored prose makes the sections semantically distinct.
The larger sections increase prompt context when several categories are selected, so the design
keeps each section bounded, removes unnecessary repetition from use cases, and verifies the source
assets directly rather than changing runtime orchestration.

---

## 4. Requirements

### Functional Requirements

1. Register exactly five new IDs: `customer_market`, `business_model_monetization`,
   `brand_positioning`, `distribution_sales`, and `customer_relationship_service`.
2. Map each ID to a same-named packaged Markdown file.
3. Each business prompt asset has one `Description` of six-to-eight sentences, category-specific
   `Why use / use cases`, `Generation requirements`, `Candidate shape`, `Valid suggestion
   directions`, `Things to consider` with eight-to-ten bullets, `Alignment check`, and `When not to
   use` guidance.
4. Each of the four new generation sections is approximately twice the earlier guidance target:
   `Generation requirements` is about 200-340 words, `Candidate shape` about 240-400 words,
   `Valid suggestion directions` about 160-320 words, and `Alignment check` about 200-340 words.
   Small variance is acceptable when needed for readable, non-repetitive prose.
5. The four sections are specific to the category's primary mechanism, not shared boilerplate.
   Requirements state non-negotiable ingredients, shape maps those ingredients to candidate fields,
   directions provide distinct mechanisms, and alignment check distinguishes the category from its
   siblings.
6. Each asset adds evidence/assumption handling, required-context signals, weak-suggestion
   patterns, or success signals when those ideas are not already covered by the required sections.
   Optional sections should add evidence or evaluation guidance rather than inflate the prompt with
   duplicated prose.
7. The prompts include the caller-supplied considerations, distinguish adjacent categories, and
   instruct the model to label missing evidence instead of inventing it.
8. Category listing and `--category` validation expose the five entries without an SDK/provider.
9. The wheel verification lists all five new files explicitly, and the offline suggestion suite
   verifies the required structure in all six PR-touched business prompt assets.

### Non-Functional Requirements

- Preserve registry ordering and deterministic prompt concatenation.
- Keep category prose in Markdown; Python only owns identifiers, loading, and validation.
- The canonical gate must pass without changing lint baselines.

---

## 5. High-Level Design

Add five `CategoryDefinition` records to the registry and maintain six prompt assets under the
existing category directory. The category command, request builder, and service already consume the
registry, so no new dispatch path is needed. Update the offline suite and wheel check to prove that
registry, source assets, installed assets, and CLI listing agree. The prompt assets remain the only
place where model-facing prose is authored.

```text
[CategoryDefinition registry]
          |
          +--> [CLI list/validate]
          +--> [selected prompt section]
          +--> [generator context]
          +--> [wheel verification]
```

---

## 6. Detailed Design

### 6.1 Registry Entries

**File(s):** `src/vidbyte_cli/services/suggestions/categories.py`
**Type:** Modified

#### What it does

Adds the five IDs, titles, concise summaries, and prompt names to the single category vocabulary.

#### Interface / API

```python
CategoryDefinition("customer_market", "Customer and Market", summary, "customer_market")
```

#### Logic / Algorithm

1. Append the entries after `business_growth` and before `product_experience`.
2. Preserve exact IDs and display order.
3. Leave `ids`, `definitions`, `require_known`, and `prompt_section` behavior unchanged.

#### Edge Cases & Error Handling

- Duplicate or unknown IDs remain rejected by the existing closed-set validator.
- `--all-categories` renders all 36 entries in registry order.

### 6.2 Prompt Assets

**File(s):** the five new category files listed in Section 9 and the modified
`business_growth.md`
**Type:** New and modified

#### What it does

Provides model-facing definitions, use cases, generation instructions, category-specific candidate
shapes, valid idea mechanisms, considerations, alignment tests, and exclusion boundaries.

#### Interface / API

```text
# <Title>
## Description
## Why use / use cases
## Generation requirements
## Candidate shape
## Valid suggestion directions
## Evidence and assumptions
## Things to consider
## Alignment check
## Weak suggestion patterns
## When not to use
```

The optional `Evidence and assumptions` and `Weak suggestion patterns` sections are included where
they clarify a distinct failure mode. They may be omitted only when the required sections already
cover the same behavior without repetition.

#### Logic / Algorithm

1. Define customer/market around who has the problem, the use situation, current alternatives, and
   evidence that demand is worth testing.
2. Define business model/monetization around value capture, pricing units, payer/user roles, cost
   structure, recurring economics, and bounded pricing experiments.
3. Define brand/positioning around remembered identity, alternatives, a meaningful difference,
   credible proof, and a testable customer-facing claim.
4. Define distribution/sales around discovery, channel fit, trust, buying friction, funnel stages,
   ownership, and repeatable acquisition economics.
5. Define relationship/service around onboarding, support, education, recovery, retention, renewal,
   advocacy, customer effort, and service capacity.
6. For each asset, write `Generation requirements` as 10-14 imperative bullets of roughly 200-340
   words; require the category's objects, causal mechanism, evidence, uncertainty, and outcome.
7. Write `Candidate shape` as 10-14 field-oriented bullets of roughly 240-400 words; explain what
   the summary, action sequence, decision points, considerations, dependencies, assumptions,
   evidence references, and completion criterion mean in this category.
8. Write `Valid suggestion directions` as 12-16 concise mechanism directions of roughly 160-320
   words; vary the mechanisms without turning the section into a list of finished suggestions.
9. Write `Alignment check` as roughly 200-340 words: state the positive primary-mechanism test,
   list category-specific near misses, and route those misses to the correct sibling or umbrella.
10. Add evidence, context, failure-mode, and success-signal guidance when it contributes something
    not already stated in those four sections.
11. Give every asset explicit sibling and umbrella boundaries, and preserve the existing C004
    description and consideration shape.

#### Edge Cases & Error Handling

- A prompt must not turn an unsupported market assumption into a fact.
- A product-interaction idea belongs to `product_experience` unless its primary mechanism is
  commercial value capture or relationship design.
- A cross-cutting growth plan belongs to `business_growth`.
- A prompt may be long, but it must not repeat the same requirement in multiple sections merely to
  meet a word target; the sections must have separate jobs.
- A section that falls below its target should fail the focused offline structure check rather than
  being padded with generic business language.

### 6.3 Verification and Packaging

**File(s):** `scripts/test_suggestions.py`, `scripts/run_ci.py`, `README.md`
**Type:** Modified

#### What it does

Checks that the five entries are visible, selectable, structurally valid, and included in the wheel,
and that all six business prompt assets touched by this PR contain the expanded structure with
category-specific minimum word bands.

#### Logic / Algorithm

1. Change the registry count assertion from 31 to 36.
2. Assert all five IDs and prompt assets exist.
3. Add one selected-category and one CLI listing assertion for the new values.
4. Add the five paths to `_WHEEL_RUNTIME_PROMPTS`.
5. Document the 36-lens vocabulary in README where the count is described.
6. Add a structure table for the six PR-touched business prompt assets, requiring the four new
   headings and their word bands, plus the existing title, description, considerations, and
   exclusion sections.
7. Assert that selected prompt text contains category-specific anchor terms and does not collapse
   into one shared section body.

#### Edge Cases & Error Handling

- A missing asset fails both registry verification and the wheel check.
- A malformed prompt fails C004 before a model run.
- A short or missing generation section fails the focused prompt-contract check before a model run.
- A copied section can pass headings and length but must fail the anchor/distinctness assertion.

---

## 7. Data Model Changes

N/A - Category definitions are static registry data and do not alter persisted records or result
schemas.

---

## 8. API Changes

No HTTP API changes. The CLI's existing `--category` closed value set grows by five values, and the
category-list result grows from 31 to 36 entries.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-business-categories.md` | Record this focused PR's contract. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/customer_market.md` | Customer and market prompt. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/business_model_monetization.md` | Business model and monetization prompt. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/brand_positioning.md` | Brand and positioning prompt. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/distribution_sales.md` | Distribution and sales prompt. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/customer_relationship_service.md` | Customer relationship and service prompt. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/business_growth.md` | Apply the same generation contract to the commercial umbrella prompt. |
| MODIFY | `src/vidbyte_cli/services/suggestions/categories.py` | Register five categories. |
| MODIFY | `scripts/test_suggestions.py` | Verify 36 categories and new selections. |
| MODIFY | `scripts/run_ci.py` | Verify new assets in the wheel. |
| MODIFY | `README.md` | Document the expanded vocabulary. |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Assert exactly 36 unique IDs and five exact new IDs.
- [Hidden Failure] Every registry prompt resolves to a non-empty asset.
- [Silent Failure] Each selected new category renders its own title and no sibling title.
- [Hidden Assumption] Unknown and duplicate new IDs fail before provider work.
- [Edge Case] All-category rendering preserves registry order.
- [Hidden Failure] C004 catches a missing description or too few considerations in a new asset.
- [Silent Failure] Human/JSON category listing includes all five new entries.
- [Edge Case] Each of the six PR-touched business assets has all required headings and stays
  inside the declared word band for each expanded section.
- [Hidden Failure] A prompt with headings but an empty or generic section body fails the focused
  anchor-term and distinctness checks.
- [Silent Failure] A category's `Candidate shape` names the fields the generator actually returns
  and does not silently omit evidence, assumptions, or completion guidance.
- [Hidden Assumption] Missing context is handled as a labeled assumption or discovery action in
  every business category rather than being converted into a factual claim.

### Integration Tests

- Run `scripts/test_suggestions.py` with the fake SDK.
- Run `python lint/run.py --rule C004` and the full `python scripts/run_ci.py` gate.
- Inspect the built wheel for all five new Markdown paths.
- Run the focused prompt-contract checks against source files and against the installed wheel copy,
  confirming that section names, minimum word bands, and category anchors survive packaging.

### Manual / QA Test Cases

1. Run `agents suggest categories --view-all` and verify the five focused business lenses are
   readable and distinct.
2. Run each `--category` individually and confirm its generator context contains only that prompt.
3. Use a pricing goal and verify the result can select monetization separately from general growth.
4. Select multiple business categories and inspect the rendered context for complete sections,
   clear category-specific mechanisms, and no accidental cross-category instructions.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing C004 lint rule | Local | Validate category structure. | It checks structure, not semantic overlap; review prose manually. |
| Setuptools package-data glob | Existing | Include Markdown assets. | Explicit wheel paths remain necessary. |

No new dependency or external service.

---

## 12. Rollout & Deployment

- Target `main` independently; this PR does not depend on the round-limit implementation.
- This is an update to PR #59. Work from its live head branch, then push the commits back to that
  branch so the existing PR receives the design amendment and implementation.
- Reconcile the in-flight prompt-depth branch before changing shared existing prompt files.
- No migration or feature flag is required. Revert the PR to roll back.

---

## 13. Open Questions

- [ ] Should `business_growth` eventually be removed from the public list? Recommendation: retain it
  for cross-cutting plans.
- [ ] Should category prompts be authored on the prompt-depth branch first? Recommendation: yes if
  that branch lands before this one; otherwise port only its structure, not unrelated edits.
- [ ] Should the four-section contract later become mandatory for all 36 categories? This PR keeps
  the migration limited to the six business assets touched by PR #59 so the context-size increase
  can be reviewed before broad adoption.

---

## 14. Alternatives Considered

### Alternative 1: Replace `business_growth`

- What: Rename the broad category into the five focused categories.
- Why rejected: Existing callers may rely on the broad ID, and cross-cutting growth ideas still need
  a home.

### Alternative 2: Store the New Prompts in Python

- What: Add long prompt strings to `categories.py`.
- Why rejected: The repository requires model-facing prose to be reviewable packaged Markdown.

### Alternative 3: Add One `business_ideas` Category

- What: Use one category and ask the model to choose the commercial mechanism internally.
- Why rejected: It would not give callers or the generator the requested distinct lenses.
