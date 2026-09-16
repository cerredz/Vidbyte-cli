# Design: split the suggestion workflow into stage collaborators

## Problem

`SuggestionService` currently owns provider calls, generation, revision,
critique policy, selection, handoff refresh, result construction, and loop
accounting in one module. That makes stage-specific changes hard to review and
encourages context, provider, and output concerns to drift together.

## Scope

Keep `SuggestionService` as the public facade and move stage responsibilities
into four focused collaborators:

- `SuggestionGeneratorAgent` builds generator/revision contexts and prompts,
  validates revision joins, and converts drafts into ideas;
- `SuggestionCritiqueAgent` builds critic calls and owns the keep/revise/reject
  policy;
- `SuggestionContextBridge` remains the only stage-aware context projection;
- `SuggestionResultBuilder` owns reviewed-idea merging, final selection,
  handoff refresh, status, warnings, and the versioned result envelope.

The facade retains loop orchestration and the shared SDK adapter because those
concerns account for all turns and enforce caller-owned token/time limits. Each
collaborator receives typed inputs and a narrow async call callback, so tests
can replace one stage without constructing a provider.

## Design

Create `generator_agent.py`, `critique_agent.py`, and `result.py`; keep public
behavior and serialized contracts stable. The generator collaborator composes
the existing context bridge, prompt library, and handoff builder. The critic
collaborator composes the category registry, prompt library, and review policy.
The result builder composes selection and handoff services and receives the
request context only when finalizing output. `service.py` then becomes a thin
facade plus the bounded iterative loop and common SDK call accounting.

## Verification

Retain the existing offline and full CI suites, and add collaborator-level
tests for initial generation, targeted revision, critique decisions, merge
ordering, and result construction. Assert the service wires all four
collaborators and no longer contains duplicate stage implementations.

## Risks and mitigations

- A refactor could change call order or stop reasons: preserve the current loop
  and move code without changing its branches.
- Shared mutable state could leak between stages: collaborators stay
  stateless per run and exchange frozen Pydantic values.
- A future stage may bypass the context boundary: require every model call to
  arrive through the callback with a bridge-produced primitive.

## Future direction: the critic stops mapping to individual ideas

`SuggestionCritiqueAgent.review` currently maps one critique onto one candidate
and derives keep, revise, and drop decisions from it. A later PR replaces that
with a single general critic handoff appended to the generator's context window
through the `vidbyte-sdk` context window manager. The critic then influences the
next generator turn as additional context rather than as a control signal, and
this module loses its per-idea mapping along with the hard-reject and duplicate
branches.

That change is deliberately out of scope here. This PR is a structural split
that must preserve the current loop's branches, and the review policy is the
part of the loop with the most behavior riding on it. Moving the boundary and
rewriting the policy in one diff would make it impossible to tell a refactor
regression from an intended policy change, so the policy is moved intact and
replaced separately.
