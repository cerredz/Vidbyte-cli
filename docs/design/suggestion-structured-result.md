# Structured Suggestion Result

## 1. Objective

Make the suggestion agent's final value a typed, deterministic object that
contains the full flat slate and a category-grouped view. Keep machine clients
from parsing a large human string while retaining a concise `to_string()` method
for terminals and logs.

## 2. User-visible behavior

`SuggestionService.run()` continues to return `SuggestionResult`, now with a
`suggestions` tuple of category groups. Each group has a stable category key and
an ordered tuple of complete `SuggestionIdea` values. `SuggestionResult.ideas`
remains as a compatibility flat view, and `to_string()` renders the same data in
rank order. JSON output includes the structured groups and remains versioned.

## 3. Scope and non-goals

In scope: Pydantic group type, result validation, deterministic grouping,
string rendering, and renderer/tests. Out of scope: changing ranking, provider
prompts, handoff shape, or the generator's tool store.

## 4. Existing behavior and constraints

The service already performs host-side validation, evidence filtering,
deduplication, horizon filtering, and ranking. The renderer serializes the
Pydantic result to JSON and separately formats human output. Existing handoff
commands consume `result.ideas`; that path must remain valid during migration.

## 5. Proposed design

Add frozen `SuggestionCategoryGroup(category, suggestions)` and a `suggestions`
field on `SuggestionResult`. A model validator normalizes either representation:
when only flat ideas are supplied it groups them in first-seen rank order; when
only groups are supplied it reconstructs the flat view; when both are supplied
they must flatten identically. Empty results have empty groups.

The service constructs groups after deterministic final ranking. Group order is
the first appearance of each category in ranked ideas; suggestion order inside a
group follows rank. `to_string()` prints status, goal, each category, title, ID,
and first action, without changing or re-ranking data.

## 6. Detailed changes

### 6.1 Add the group model

**File:** `src/vidbyte_cli/types/suggestions.py`

Define the strict frozen group model and export it. Enforce a non-empty category
and a bounded tuple of ideas. Add the normalization validator and `to_string()`
on `SuggestionResult`.

### 6.2 Build the structured view

**File:** `src/vidbyte_cli/services/suggestions/service.py`

Populate `suggestions` from the final tuple in `_result`, including dry-run and
partial results. Use one helper so every stop reason receives the same shape.

### 6.3 Render and verify

**Files:** renderer, offline suggestion script, CI manifest if needed

Use `result.to_string()` for human output, retain the JSON envelope's Pydantic
serialization, and test round trips, category ordering, empty output, and the
flat compatibility view. Tests must verify that structured values are complete
`SuggestionIdea` objects rather than title-only projections.

## 7. Alternatives considered

1. Return only a string: rejected because callers need typed category and idea
   fields without reparsing presentation text.
2. Replace `ideas` immediately: rejected because the handoff command and clients
   already rely on the flat view; normalization allows a safe migration.
3. Use an untyped dictionary: rejected because Pydantic validation, JSON schema,
   and strict nested bounds are part of the existing service contract.

## 8. Risks and mitigations

- Duplicating flat and grouped fields can drift; the model validator rejects a
  mismatch and tests exercise both construction directions.
- Adding groups enlarges JSON output; it is a deliberate additive contract and
  the complete idea objects are not copied into a second process.
- Human formatting can accidentally become authoritative; `to_string()` is
  explicitly presentation-only and ranking remains host-controlled.

## 9. Observability and failure semantics

Malformed group/flat combinations fail at the typed result boundary before
rendering. `to_string()` is deterministic for identical results and does not
include warnings or provider internals beyond the typed stop reason. Existing
status, usage, warning, and stop-reason fields remain authoritative.

## 10. Testing strategy

- **Edge case:** grouped construction preserves first-seen category order and
  rank order within each group.
- **Hidden failure:** mismatched flat and grouped values raise Pydantic validation
  errors rather than silently selecting one representation.
- **Silent failure:** a result with no ideas has no phantom category groups and a
  stable empty string.
- **Hidden assumption:** existing `result.ideas` and handoff lookup behavior are
  unchanged.

Run focused tests, strict typing, lint, and the canonical clean-wheel CI gate.

## 11. Rollout and rollback

This is an additive output contract; consumers can adopt `suggestions` while
using `ideas` during migration. Reverting the PR removes the group field without
data migration.

## 12. Open questions and resolved decisions

- [x] Keep `ideas` as a compatibility flat view for this PR.
- [x] Name the grouped field `suggestions` and the nested model
  `SuggestionCategoryGroup`.
- [x] Keep `to_string()` presentation-only and deterministic.
- [x] Group only after final host-side selection and ranking.

## 13. Implementation checklist

- [ ] Add the strict group model and result normalization.
- [ ] Populate groups from the service and dry-run path.
- [ ] Route human rendering through `to_string()`.
- [ ] Add edge, hidden-failure, and compatibility tests.
- [ ] Run refinement review and the full CI gate.

## 14. Traceability

This design addresses suggestion-agent planning item 17: the returned value is a
Pydantic structured object with category groups and complete suggestion objects,
plus a safe string representation for presentation contexts.
