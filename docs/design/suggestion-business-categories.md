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
business-and-growth category remains available for cross-cutting commercial ideas.

---

## 2. Goals & Non-Goals

### Goals

- Add five unique category IDs and one prompt asset per ID.
- Turn the supplied descriptions and questions into the repository's full category prompt shape.
- State boundaries against `business_growth`, `product_experience`, and the new sibling categories.
- Keep category listing, selection, validation, packaging, and agent rendering data-driven.

### Non-Goals

- No changes to generation, critique, context, result, or service orchestration.
- No removal or renaming of existing category IDs.
- No market research or factual claims beyond the category guidance itself.

---

## 3. Background & Context

The merged suggestion agent currently exposes 31 categories and one Markdown asset for each. Its
`business_growth` and `product_experience` prompts are useful but broad, so commercial requests
about audience, pricing, message, channel, or post-purchase value collapse into one lens. The new
categories make those decisions independently selectable and easier for the generator to vary.

The repository's C004 rule requires every category asset to have one title, a six-to-eight sentence
description, and eight-to-ten considerations. The existing `feat/suggestion-category-prompts`
branch deepens the current 31 assets; this PR preserves that work's structure for the five new
assets and narrows the broad business-growth boundary.

---

## 4. Requirements

### Functional Requirements

1. Register exactly five new IDs: `customer_market`, `business_model_monetization`,
   `brand_positioning`, `distribution_sales`, and `customer_relationship_service`.
2. Map each ID to a same-named packaged Markdown file.
3. Each file has a six-to-eight sentence `Description`, eight two-to-three sentence items under
   `Why use / use cases`, eight-to-ten `Things to consider` bullets, and `When not to use` guidance.
4. The prompts include the caller-supplied considerations and distinguish adjacent categories.
5. Category listing and `--category` validation expose the five entries without an SDK/provider.
6. The wheel verification lists all five new files explicitly.

### Non-Functional Requirements

- Preserve registry ordering and deterministic prompt concatenation.
- Keep category prose in Markdown; Python only owns identifiers, loading, and validation.
- The canonical gate must pass without changing lint baselines.

---

## 5. High-Level Design

Add five `CategoryDefinition` records to the registry and five prompt assets under the existing
category directory. The category command, request builder, and service already consume the registry,
so no new dispatch path is needed. Update the offline suite and wheel check to prove that registry,
source assets, installed assets, and CLI listing agree.

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

**File(s):** five files listed in Section 9
**Type:** New

#### What it does

Provides model-facing definitions, use cases, considerations, and exclusion boundaries.

#### Interface / API

```text
# <Title>
## Description
## Why use / use cases
## Things to consider
## When not to use
```

#### Logic / Algorithm

1. Define customer/market around who has the problem and where demand exists.
2. Define business model/monetization around value capture, pricing, costs, and cadence.
3. Define brand/positioning around remembered identity, alternatives, and demonstrable difference.
4. Define distribution/sales around discovery, trust, channels, and buying friction.
5. Define relationship/service around onboarding, support, retention, renewal, and advocacy.
6. Give every asset explicit sibling and umbrella boundaries.

#### Edge Cases & Error Handling

- A prompt must not turn an unsupported market assumption into a fact.
- A product-interaction idea belongs to `product_experience` unless its primary mechanism is
  commercial value capture or relationship design.
- A cross-cutting growth plan belongs to `business_growth`.

### 6.3 Verification and Packaging

**File(s):** `scripts/test_suggestions.py`, `scripts/run_ci.py`, `README.md`
**Type:** Modified

#### What it does

Checks that the five entries are visible, selectable, structurally valid, and included in the wheel.

#### Logic / Algorithm

1. Change the registry count assertion from 31 to 36.
2. Assert all five IDs and prompt assets exist.
3. Add one selected-category and one CLI listing assertion for the new values.
4. Add the five paths to `_WHEEL_RUNTIME_PROMPTS`.
5. Document the 36-lens vocabulary in README where the count is described.

#### Edge Cases & Error Handling

- A missing asset fails both registry verification and the wheel check.
- A malformed prompt fails C004 before a model run.

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

### Integration Tests

- Run `scripts/test_suggestions.py` with the fake SDK.
- Run `python lint/run.py --rule C004` and the full `python scripts/run_ci.py` gate.
- Inspect the built wheel for all five new Markdown paths.

### Manual / QA Test Cases

1. Run `agents suggest categories --view-all` and verify the five focused business lenses are
   readable and distinct.
2. Run each `--category` individually and confirm its generator context contains only that prompt.
3. Use a pricing goal and verify the result can select monetization separately from general growth.

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
- Reconcile the in-flight prompt-depth branch before changing shared existing prompt files.
- No migration or feature flag is required. Revert the PR to roll back.

---

## 13. Open Questions

- [ ] Should `business_growth` eventually be removed from the public list? Recommendation: retain it
  for cross-cutting plans.
- [ ] Should category prompts be authored on the prompt-depth branch first? Recommendation: yes if
  that branch lands before this one; otherwise port only its structure, not unrelated edits.

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
