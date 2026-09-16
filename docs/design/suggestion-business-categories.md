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
- Give all 36 category prompt assets in the live PR #59 tree the same generation contract:
  `Generation requirements` and `Alignment check`.
- Make each of those sections materially deep enough to guide generation rather than merely label
  the category, with category-specific content rather than copied boilerplate.
- Keep both sections about the suggestion category itself. Candidate field shape belongs to the
  generator prompt and the handoff, which already render it, so no category asset restates it.

### Non-Goals

- No changes to generation, critique, context, result, or service orchestration.
- No removal or renaming of existing category IDs.
- No market research or factual claims beyond the category guidance itself.
- No changes to category identifiers, registry ordering, loader behavior, or generated result
  schemas while expanding the prompt assets.

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

The requested follow-up therefore adds four long, category-specific sections to every one of the 36
category assets in the live PR tree. The repeated headings make the assets easy to inspect, while
the tailored prose makes the sections semantically distinct. The larger sections increase prompt
context when several categories are selected, so the design keeps each section bounded, removes
unnecessary repetition from use cases, and verifies the source assets directly rather than changing
runtime orchestration.

---

## 4. Requirements

### Functional Requirements

1. Register exactly five new IDs: `customer_market`, `business_model_monetization`,
   `brand_positioning`, `distribution_sales`, and `customer_relationship_service`.
2. Map each ID to a same-named packaged Markdown file.
3. Each of the 36 category prompt assets has one `Description` of six-to-eight sentences,
   category-specific `Why use / use cases`, `Things to consider` with eight-to-ten bullets,
   `Generation requirements`, `Alignment check`, and `When not to use` guidance, in that order.
4. `Generation requirements` opens with a substantial paragraph explaining why the category imposes
   the requirements it does, then lists them; the whole section runs at least 260 words.
   `Alignment check` is one or two paragraphs of prose of at least 200 words.
5. Both sections are specific to the category's primary mechanism, not shared boilerplate.
   Requirements state the non-negotiable ingredients of a suggestion in this category, and the
   alignment check explains what alignment means here and distinguishes the category from siblings.
6. Neither section carries output shape, environment, or run information. The candidate's fields,
   the use of supplied context, and assumption labelling are contracts of the generator prompt and
   the handoff, so a category asset that repeats them makes one contract editable in two places.
7. The prompts include the caller-supplied considerations, distinguish adjacent categories, and
   instruct the model to label missing evidence instead of inventing it.
8. Category listing and `--category` validation expose the five entries without an SDK/provider.
9. The wheel verification lists all 36 category files explicitly, and the offline suggestion suite
   verifies the required structure in every category prompt asset.

### Non-Functional Requirements

- Preserve registry ordering and deterministic prompt concatenation.
- Keep category prose in Markdown; Python only owns identifiers, loading, and validation.
- The canonical gate must pass without changing lint baselines.

---

## 5. High-Level Design

Add five `CategoryDefinition` records to the registry and maintain all 36 prompt assets under the
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

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/categories/*.md` (36 assets)
**Type:** New and modified

#### What it does

Provides model-facing definitions, use cases, generation instructions, category-specific candidate
shapes, valid idea mechanisms, considerations, alignment tests, and exclusion boundaries.

#### Interface / API

```text
# <Title>
## Description
## Why use / use cases
## Things to consider
## Generation requirements
## Alignment check
## Weak suggestion patterns
## When not to use
```

The optional `Weak suggestion patterns` section is included where it names a distinct failure mode
the required sections do not already cover. `Generation requirements` and `Alignment check` are
present in all 36 files, and no file carries a `Candidate shape`, `Valid suggestion directions`, or
`Evidence and assumptions` section.

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
6. For each asset, open `Generation requirements` with a paragraph explaining why the category
   imposes its requirements — what it exists to protect and how suggestions in it fail — then list
   nine or more imperative requirements of the suggestion itself: the category's objects, causal
   mechanism, uncertainty, and outcome. Keep the section at 260 words or more.
7. Write `Alignment check` as one or two prose paragraphs of 200 words or more. Explain what
   alignment means for this category in plain terms, so a reader who knows nothing else can tell
   whether a candidate belongs, then name the sibling categories that near misses route to.
8. Add weak-suggestion or success-signal guidance only when it contributes something not already
   stated in those two sections.
9. Give every asset explicit sibling and umbrella boundaries, and preserve the existing C004
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
and that all 36 category prompt assets contain the expanded structure with category-specific minimum
word bands.

#### Logic / Algorithm

1. Change the registry count assertion from 31 to 36.
2. Assert all five IDs and prompt assets exist.
3. Add one selected-category and one CLI listing assertion for the new values.
4. Add the five paths to `_WHEEL_RUNTIME_PROMPTS`.
5. Document the 36-lens vocabulary in README where the count is described.
6. Add a structure table for all 36 category prompt assets, requiring the four new headings and
   their word bands, plus the existing title, description, considerations, and exclusion sections.
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
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/*.md` | Apply the expanded generation contract to every one of the 36 category assets. |
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
- [Edge Case] Each of the 36 category assets has all required headings and clears the word floor
  for each expanded section.
- [Hidden Failure] A prompt with headings but an empty or generic section body fails the focused
  anchor-term and distinctness checks.
- [Silent Failure] A reinstated `Candidate shape` or `Valid suggestion directions` section fails
  the removed-section check, so the candidate contract cannot drift back into the category assets.
- [Hidden Failure] A bulleted reroute table reintroduced into `Alignment check` fails the prose
  check, because it is the shape the explanatory paragraphs replaced.

### Integration Tests

- Run `scripts/test_suggestions.py` with the fake SDK.
- Run `python lint/run.py --rule C004` and the full `python scripts/run_ci.py` gate.
- Inspect the built wheel for all five new Markdown paths.
- Run the focused prompt-contract checks against all source files and against the installed wheel
  copy, confirming that section names, minimum word bands, and category anchors survive packaging.

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
- [ ] Should the four-section contract later become mandatory for non-category prompt assets as
  well? This PR limits the migration to the 36 category assets because those are the reusable
  taxonomy contracts supplied to the suggestion generator.

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
