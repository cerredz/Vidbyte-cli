# Design: prune suggestion-agent context by stage

## Problem

`SuggestionService` currently places the full request snapshot in every model
context window. The snapshot contains caller-only metadata (source paths,
labels, descriptions, manifest details, and workflow limits) and the critic
and revision turns repeat candidate JSON in both the prompt and context. This
uses context budget without improving the model's decision.

## Scope

Add a `SuggestionContextBridge` that builds the smallest context primitive for
each stage while preserving the existing request and result contracts:

- generator windows contain the selected category guidance and each supplied
  record's stable evidence reference, kind, and content;
- critic windows additionally contain a compact candidate projection needed to
  verify evidence, constraints, actionability, and distinctness;
- revision windows contain only revisable candidate projections and their
  critique packets, with stable candidate IDs for the service join;
- manifest fields, source paths, caller/file provenance, descriptions, hashes,
  character limits, settings, rankings, handoff execution prompts, and other
  result-only metadata never enter a model context window.

The bridge remains deterministic and does not mutate the request snapshot.
Candidate IDs and context references are retained only where the workflow
needs them to join a model response back to typed local state.

## Design

Create `services/suggestions/context_bridge.py` with a small value-oriented
collaborator. It returns `SuggestionContextPrimitive` values built from
redacted item views and stable, sorted JSON projections. `to_context_text()`
will render only the role-relevant body, never `SuggestionContextItem.source`,
`label`, or `description`.

The service and extra-compute path will use the bridge for generator,
critic, and revision calls. Revision prompt templates will carry only the
goal and requested count; candidates and critiques live in the revision
context exactly once. Existing final results and manifests remain unchanged.

## Verification

Add offline tests that assert stage-specific inclusion/exclusion, stable
ordering, no mutation of the caller snapshot, and a materially smaller
rendered context than the current full snapshot. Keep the SDK boundary test,
category fan-out test, and handoff tests passing.

## Risks and mitigations

- Removing evidence references would make critique impossible: preserve
  run-local context refs and candidate IDs as explicit join keys.
- A provider may rely on prompt placeholders: update the revision template and
  test rendered prompts for the single-payload invariant.
- Future fields may accidentally leak: keep projection allowlists and tests
  that assert known metadata is absent.
