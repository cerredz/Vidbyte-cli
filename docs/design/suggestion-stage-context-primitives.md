# Design: stage-specific suggestion context primitives

## Problem

`SuggestionService` placed the full caller snapshot in every model context
window. That snapshot exists for the caller: it carries source paths, labels,
descriptions, manifest data, and the run's goal. The critic and revision turns
then repeated candidate JSON in both the prompt and the context. None of that
improves the model's decision, and all of it spends context budget.

## Scope

Give the workflow its own context primitive instead of pruning the caller's:

- `SuggestionAgentContext` is the only primitive the SDK boundary accepts, and
  it declares exactly four fields a model may read — a description, evidence,
  the selected category block, and, where the stage needs them, candidates and
  critiques;
- generator windows carry evidence and category guidance only;
- critic windows add the candidates under review;
- revision windows add those candidates and their matching critiques;
- `SuggestionContextPrimitive` goes back to being the caller snapshot alone and
  loses `candidate_handoffs`, a field only an agent window ever needed.

## Design

Candidates travel as `SuggestionDraft` and critiques as `SuggestionCritique` —
the same contracts the generator and critic already return. Reusing them is
what keeps workflow state out of a window: `SuggestionDraft` has no field for
rank, revision, review summary, or handoff, so `SuggestionIdea.to_draft()`
cannot carry one through. Likewise `SuggestionAgentContext` has no field for a
source path, a label, a manifest entry, or run metadata, so no stage can place
one. Exclusion is a property of the types rather than of an allowlist that a
later field would silently escape.

`SuggestionAgentContext.for_stage()` builds one window from the caller snapshot
and the rendered category block without mutating either. `to_context_text()`
renders the category block, each evidence record as `[ref] kind` plus its body,
and one compact sorted JSON packet per populated model tuple. The revision
prompt template carries the goal and requested count; candidates and critiques
appear exactly once, in the context.

## Verification

`scripts/test_suggestions.py` asserts stage-specific inclusion and exclusion,
that a rendered window keeps evidence bodies while dropping caller metadata,
that the caller snapshot is unchanged after a run, and that the revision prompt
no longer repeats the packet. The SDK boundary, category fan-out, and handoff
tests continue to pass unchanged.

## Risks and mitigations

- Removing evidence references would make critique impossible: `ref` and
  `idea_id` stay in the window as the workflow's join keys.
- A provider may rely on prompt placeholders: the revision template was updated
  with the code, and a test reads the rendered prompt.
- A new field on `SuggestionDraft` reaches models automatically: that is the
  intended coupling — the draft contract is the candidate contract, and any
  field a model should not see belongs on `SuggestionIdea` instead.
