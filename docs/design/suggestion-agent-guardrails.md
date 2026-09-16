# Suggestion Agent Guardrails

## 1. Objective

Add explicit execution guardrails around the suggestion workflow so a provider,
tool-enabled curator, or malformed response cannot consume unbounded calls or
leave the caller without a typed outcome. This PR builds on the generator-owned
curation branch and keeps the final result shape unchanged.

## 2. User-visible behavior

Callers may set an agent-call cap and a tool-call cap. The result identifies
whether the run stopped because of rounds, tokens, time, agent calls, or tool
calls. A limit reached after a committed snapshot returns that snapshot as a
partial result with a warning. Existing input validation and dry-run behavior
remain unchanged.

## 3. Scope and non-goals

In scope: typed settings and CLI options, counters, store enforcement, stop
reasons, and deterministic partial-result handling. Out of scope: retries,
provider-specific backoff, a persistent budget service, or changing category
selection and final result schemas.

## 4. Existing behavior and constraints

The service already checks rounds, aggregate tokens, and wall-clock time. The
curation store has a hard-coded tool-call cap, while the service has no explicit
cap on total agent turns. SDK timeout and cancellation semantics must remain the
SDK adapter's concern; a cancellation must not be converted into a successful
result.

## 5. Proposed design

Add `max_agent_calls` and `max_tool_calls` to `SuggestionSettings`, with bounded
defaults and CLI plumbing. `_call_agent` checks the agent budget before creating
a new agent and records every completed turn. `SuggestionStore` receives the
validated tool budget and raises a typed internal limit when it is exhausted.
The workflow catches these limits at transaction boundaries, finalizes the last
committed store snapshot, and returns the matching stop reason and warning.

The existing rounds/tokens/time checks remain independent. A limit is checked
before a call, so the configured cap is never exceeded. The initial generation
and independent critic remain fatal provider failures when no committed slate
exists; curation failures preserve the last committed slate as implemented by
the preceding PR.

## 6. Detailed changes

### 6.1 Add typed stop reasons and settings

**Files:** `src/vidbyte_cli/types/suggestions.py`

Add `AGENT_CALL_LIMIT` and `TOOL_CALL_LIMIT`. Add positive, bounded settings
fields with defaults that preserve current behavior. Keep Pydantic `extra="forbid"`
so callers cannot silently misspell a budget.

### 6.2 Expose CLI controls

**Files:** request builder, suggest command, two help prompt assets

Add `--max-agent-calls` and `--max-tool-calls`, validate integer bounds before
provider loading, and pass values unchanged into `SuggestionSettings`.

### 6.3 Enforce agent calls

**File:** `src/vidbyte_cli/services/suggestions/service.py`

Check the cap at the same boundary as tokens/time and include the initial,
critic, and curation phases in the same counter. Convert a pre-call exhaustion
into `AGENT_CALL_LIMIT` with the committed snapshot.

### 6.4 Enforce tool calls

**File:** `src/vidbyte_cli/services/suggestions/store.py`

Accept the caller's validated cap instead of a literal. Raise a private typed
exception only for budget exhaustion; retain normal validation errors for bad
category, evidence, duplicate, or ID inputs. This lets the service distinguish a
guardrail stop from a provider/tool contract failure.

### 6.5 Verify failures and accounting

**Files:** offline suggestion tests and CI manifest

Cover cap-before-call, cap-after-commit, tool-cap transaction isolation, CLI
validation, typed stop reasons, and usage counters. Add one hidden-failure test
for a curation cap and one silent-failure test proving no uncommitted mutation
leaks into the final result.

## 7. Alternatives considered

1. A single global integer constant: rejected because callers need a bounded
   per-run budget and tests need deterministic small caps.
2. Letting the SDK own the total budget: rejected because the service combines
   generation, critique, and curation and must report one stable stop reason.
3. Treating every cap as provider failure: rejected because operators need to
   distinguish deliberate budget exhaustion from transport or schema failure.

## 8. Risks and mitigations

- A low agent cap can stop before curation; the result carries the committed
  snapshot and explicit stop reason.
- A low tool cap can leave a working copy partially edited; copy-on-write means
  it is discarded unless the pass completes and commits.
- New CLI settings can enlarge the public surface; strict bounds and help text
  make the contract discoverable.
- Existing callers omitting the fields must retain current limits via defaults;
  tests assert those defaults.

## 9. Observability and failure semantics

Usage includes all attempted/completed agent turns and the existing phase
counters. Limit warnings are stable, non-sensitive strings. Provider failures
continue to use the existing typed failure path when no committed snapshot is
available; curation failures and guardrail stops return typed partial results.

## 10. Testing strategy

- **Edge case:** minimum and maximum accepted budgets; zero/over-limit values
  rejected before an agent is constructed.
- **Hidden failure:** agent-call exhaustion before curation returns the initial
  committed slate and `agent_call_limit`.
- **Silent failure:** a tool mutation made after the cap is rejected and never
  appears in the committed snapshot.
- **Hidden assumption:** default settings preserve the existing number of turns
  and store cap.

Run focused suggestion tests, ruff, mypy, lint, and the canonical clean-wheel
CI script.

## 11. Rollout and rollback

The change is additive and defaults are backward-compatible. Roll back by
reverting this PR; no persisted state or migration is involved.

## 12. Open questions and resolved decisions

- [x] Keep rounds, tokens, and time as separate independent limits.
- [x] Count every generator, critic, and curator turn in one agent budget.
- [x] Keep tool budgets run-local and transaction-safe.
- [x] Return committed partial results on curation guardrail stops.

## 13. Implementation checklist

- [ ] Add stop reasons and bounded settings.
- [ ] Add request-builder and Click options/help.
- [ ] Enforce service agent-call cap.
- [ ] Enforce store tool-call cap and typed limit.
- [ ] Add focused tests and CI registration.
- [ ] Run refinement review and the full CI gate.

## 14. Traceability

This design addresses suggestion-agent planning item 16: rounds, tokens, and
time remain supported, while call and tool budgets plus explicit failure
handling close the next unbounded-execution paths. Structured grouped output is
intentionally left for the separate item-17 PR.
