# Design Doc: Suggestion Category Prompt Depth

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-16

---

## 1. Overview

Strengthen every suggestion category prompt so the specialized suggestion agent receives enough category-specific guidance to distinguish useful suggestions from generic next-action advice. Each of the 31 packaged category assets uses the same four-part shape: a two-paragraph description of six to eight sentences per paragraph, a prose `Why use` rationale argued for that category rather than for suggestions in general, a ten-to-fifteen item `Use cases` list, and a `When not to use` list closed by a paragraph that routes the reader to the categories that fit instead. The generic `Things to consider` list is removed from every asset. This resolves the review feedback on the adjacent-opportunity prompt at the category-library level rather than leaving the other category assets with the same weakness.

---

## 2. Goals & Non-Goals

### Goals

- Give every suggestion category a two-paragraph description, each paragraph six to eight sentences, separating what the category is from how a suggestion under it must behave.
- Give every category a prose `Why use` rationale of at least two paragraphs that argues for that specific suggestion type and draws the boundary against the categories it is confused with.
- Give every category a `Use cases` list of ten to fifteen items, each a concrete trigger developed in two or three sentences.
- Close every category with a `When not to use` list of disqualifying signals followed by a paragraph naming the categories that fit instead.
- Remove the generic `Things to consider` list, which repeated broad agent behavior across the library.
- Preserve the existing one-file-per-category registry and packaged Markdown asset model.
- Verify the complete prompt library with the structural lint and the canonical CI gate.

### Non-Goals

- Do not change category identifiers, registry ordering, summaries, or prompt-loading code.
- Do not change the suggestion agent’s Python orchestration, schemas, CLI surface, or output contracts.
- Do not add a new lint rule or new feature test file; C004 is rewritten in place to gate the new shape, and the existing suggestions script is retargeted at a surviving section.
- Do not redesign generator, critic, or revision prompts outside the category asset directory.

---

## 3. Background & Context

- The suggestion agent loads one Markdown asset per selected category and places those assets in the model-facing context.
- The current category files have a short description and broad considerations, so the specialized agent receives insufficiently differentiated guidance even though the registry exposes 31 distinct categories.
- Review of PR #55 required a two-paragraph description, a split of the combined `Why use / use cases` section into a prose rationale and a longer item list, the removal of `Things to consider`, and a bulleted-then-prose `When not to use` section, and stated that the comments on `adjacent_opportunity.md` apply to every prompt in the folder.
- Review also required the `Why use` rationale to be respective to the actual category suggestion type rather than to suggestions in general, which is the requirement the old considerations list failed hardest.
- The repository’s C004 rule previously required one title, a six-to-eight sentence description, and eight-to-ten considerations, so it had to be rewritten alongside the assets; its diagnostics establish the category assets as shared model-facing contracts.
- The field guide requires authored agent vocabulary to remain in packaged Markdown, and the existing `pyproject.toml` package-data glob already includes the category directory.

---

## 4. Requirements

### Functional Requirements

1. Every Markdown file under `src/vidbyte_cli/services/suggestions/prompts/categories/` must retain exactly one level-one title naming its category.
2. Every category must contain a `## Description` section of exactly two paragraphs, each with six to eight complete sentences, defining the category’s purpose and boundary and then how a suggestion under it must behave.
3. Every category must contain a `## Why use` section of at least two prose paragraphs and no bullets, arguing for that specific suggestion type and naming the boundary against neighboring categories.
4. Every category must contain a `## Use cases` section with ten to fifteen items; each item must contain two or three complete sentences describing a concrete trigger.
5. Every category must contain a `## When not to use` section of four to eight bullets naming disqualifying signals, followed by one paragraph routing the reader to the categories that fit instead.
6. No category may contain a `## Things to consider`, `## Why use / use cases`, `## Timeline`, or `## Checklist` section.
6. The category-specific sections must distinguish neighboring categories where their purposes overlap, including explicit boundaries for timing, evidence, reversibility, effort, and decision impact when those dimensions matter.
7. Category identifiers, prompt filenames, registry mappings, loader behavior, and packaged asset declarations must remain unchanged.

### Non-Functional Requirements

- Prompt prose must be readable, concrete, and useful to a model making category-specific suggestions.
- The changes stay within the category prompt directory, the C004 rule and its catalogue row, the design documents that describe the shape, and the one assertion in `scripts/test_suggestions.py` that named the removed section.
- The existing canonical gate, `python scripts/run_ci.py`, must pass from the implementation worktree.
- The built wheel must continue to include all category Markdown assets through the existing package-data declaration.
- No credentials, network calls, API changes, or runtime side effects are introduced.

---

## 5. High-Level Design

Update each of the 31 category Markdown assets in place while preserving the existing title and filename-to-registry mapping. The prose for each asset is authored around its category’s unique decision pattern: the description defines the concept and then the behavior a suggestion must show, the `Why use` rationale argues the category against its neighbors, the `Use cases` list enumerates concrete triggers, and the `When not to use` section prevents over-application and routes the reader elsewhere. C004 is rewritten in the same change so the new shape is gated rather than merely described.

The loader and registry remain unchanged. At runtime, selected category files continue to be loaded and concatenated into the model context exactly as they are today, but each selected category will now carry deeper, more differentiated guidance. Existing C004 validation and the suggestions verification script will be used during implementation, followed by the complete CI gate and wheel-asset inspection.

```text
[Category registry] -> [one Markdown asset per selected category]
                              |
                              v
                   [specialized suggestion agent context]
```

---

## 6. Detailed Design

### 6.1 Category Prompt Assets

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/categories/*.md` (31 existing files)
**Type:** Modified

#### What it does

Each asset defines one suggestion category for the generator and category-inspection command. The asset remains plain Markdown with no template placeholders or executable behavior.

#### Interface / API

```text
# <Category title>

## Description
<paragraph one: 6-8 complete sentences defining the category and its boundary>

<paragraph two: 6-8 complete sentences on how a suggestion under it must behave>

## Why use
<paragraph on the situation this specific suggestion type is for>

<paragraph on the discipline the category enforces>

<paragraph drawing the boundary against neighboring categories>

## Use cases
- **<Trigger>.** <2-3 sentences on when this category applies>
... (10-15 items)

## When not to use
- **<Disqualifying signal>.** <one sentence on why it disqualifies>
... (4-8 bullets)

<closing paragraph naming the categories that fit instead>
```

#### Logic / Algorithm

1. Preserve the existing category title and filename.
2. Rewrite the description as two paragraphs of six-to-eight sentences: the first defines the category, its boundary, and what disqualifies a candidate; the second states the evidence and discipline a suggestion under it must carry.
3. Write `Why use` as prose paragraphs covering the situation the category is for, the discipline it enforces, and the boundary against the categories it is confused with.
4. Write ten-to-fifteen `Use cases` items, each a distinct practical trigger developed in two or three sentences.
5. Write `When not to use` as bullets of disqualifying signals followed by one paragraph naming the categories that fit instead.
6. Delete the `Things to consider` section rather than renaming it.
7. Run C004 and inspect representative rendered category output to confirm the loader still exposes the authored sections.

#### Edge Cases & Error Handling

- A category with no credible use case should be excluded by its “When not to use” guidance rather than padded with generic advice.
- Neighboring categories may share vocabulary, so each asset must state the distinguishing decision boundary instead of duplicating the overall agent’s instructions.
- Markdown headings must remain compatible with the existing category loader and C004 parser.
- No missing asset is expected because filenames and registry mappings are unchanged; the package-data verification will catch packaging regressions.

---

## 7. Data Model Changes

N/A - This change edits static Markdown prompt assets only and does not alter Python types, schemas, persistence, or stored data.

---

## 8. API Changes

N/A - No API endpoint, request, response, or CLI protocol changes are required.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-category-prompt-depth.md` | Record the requirements and implementation contract for the category prompt rewrite. |
| MODIFY | `lint/rules/c004_suggestion_category_prompt_structure.py` | Gate the new four-section shape and report the retired sections by name. |
| MODIFY | `lint/README.md` | Update the C004 catalogue row to the contract the rule now enforces. |
| MODIFY | `docs/design/suggestion-agent.md` | Update the prompt-asset description to the shape the category files now carry. |
| MODIFY | `scripts/test_suggestions.py` | Assert against a surviving section now that `Things to consider` is removed. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/adjacent_opportunity.md` | Deepen and specialize the adjacent-opportunity prompt per review feedback. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/alternative.md` | Add complete, category-specific guidance for materially different routes. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/big_bets.md` | Add complete, category-specific guidance for high-upside uncertain bets. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/bottleneck.md` | Add complete, category-specific guidance for limiting constraints. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/business_growth.md` | Add complete, category-specific guidance for reach, sustainability, revenue, and customer value. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/completion.md` | Add complete, category-specific guidance for closing unfinished obligations. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/continuation.md` | Add complete, category-specific guidance for advancing accepted plans. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/coordination.md` | Add complete, category-specific guidance for ownership and dependency alignment. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/creative_exploration.md` | Add complete, category-specific guidance for generating possibilities beyond assumptions. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/cross_domain.md` | Add complete, category-specific guidance for transferring mechanisms from another field. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/delegation.md` | Add complete, category-specific guidance for assigning work to the best owner. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/experiment.md` | Add complete, category-specific guidance for bounded tests that change decisions. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/feedback.md` | Add complete, category-specific guidance for seeking decision-relevant reactions. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/goal_clarification.md` | Add complete, category-specific guidance for defining outcomes and success signals. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/immediate_next_steps.md` | Add complete, category-specific guidance for actionable moves from the current state. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/investigation.md` | Add complete, category-specific guidance for focused evidence gathering. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/learning.md` | Add complete, category-specific guidance for targeted skill and knowledge acquisition. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/leverage.md` | Add complete, category-specific guidance for reusable assets with multiple benefits. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/long_term_directions.md` | Add complete, category-specific guidance for durable future directions. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/preparation.md` | Add complete, category-specific guidance for readiness before anticipated demands. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/prerequisite.md` | Add complete, category-specific guidance for required conditions before intended work. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/prioritization.md` | Add complete, category-specific guidance for choosing among competing commitments. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/product_experience.md` | Add complete, category-specific guidance for improving usability and user experience. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/quick_wins.md` | Add complete, category-specific guidance for small near-term payoffs. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/reframing.md` | Add complete, category-specific guidance for changing interpretation to unlock action. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/risk_prevention.md` | Add complete, category-specific guidance for proportionate failure prevention. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/simplification.md` | Add complete, category-specific guidance for removing unnecessary complexity. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/stop_or_defer.md` | Add complete, category-specific guidance for stopping or postponing low-value work. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/strategy.md` | Add complete, category-specific guidance for broader directional choices. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/technical_possibilities.md` | Add complete, category-specific guidance for technically enabled options. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/categories/verification.md` | Add complete, category-specific guidance for testing consequential claims. |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Rewritten C004 lint rule | Local `lint/rules/c004_suggestion_category_prompt_structure.py` | Validate the title, the two-paragraph description, the prose `Why use` section, the `Use cases` count, the `When not to use` bullets and closing paragraph, and the absence of retired sections. | The rule measures structure, not prose specificity, so the requirement that `Why use` argue the category rather than suggestions in general still requires review. |
| Setuptools package data | Existing `pyproject.toml` glob | Include category Markdown assets in the wheel. | A future packaging change could omit the assets even if source checks pass. |

---

## 11. Rollout & Deployment

- No feature flag or migration is required because the change is static prompt content.
- The updated assets take effect when the new CLI package is installed or when the source checkout is used.
- Rollout is the normal package build and release process after the canonical local and pull-request gates pass.
- Rollback is a revert of the prompt-content commit, followed by the same validation and package checks.

---

## 12. Open Questions

N/A - The review comment specifies the required structure and applies it to every category asset; no unresolved product or implementation decision remains.

---

## 13. Alternatives Considered

### Alternative 1: Update only `adjacent_opportunity.md`

- What: Address the inline comment only in the file where it was written.
- Why rejected: The review explicitly says the same standards apply to every category prompt, and leaving the rest shallow would preserve the agent-quality problem.

### Alternative 2: Add generic guidance in the Python service

- What: Keep category files short and compensate with shared instructions in the suggestion service.
- Why rejected: The field guide and repository architecture require model-facing prose to remain in Markdown assets, and shared instructions would not specialize the categories.

### Alternative 3: Extend C004 to enforce prose quality automatically

- What: Add structural checks for use-case item length, specialized considerations, and “When not to use.”
- Why rejected: The current request is a content rewrite, and semantic specificity is not reliably decidable with the repository’s static lint approach; existing C004 plus focused manual review is sufficient for this change.
