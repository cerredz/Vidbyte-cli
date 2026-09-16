# Design: expose actionable critic signals

## Problem

The critic currently returns a verdict, confidence, one evidence check, and a
free-form repair instruction. That is enough to control the loop, but callers
cannot tell which quality dimensions made a candidate useful, risky, weak, or
worth repairing. A single score would hide those tradeoffs and encourage
false precision.

## Scope

Extend `SuggestionCritique` with a typed signal packet and issue list while
keeping the existing control fields backward compatible:

- quality dimensions: goal alignment, category fit, evidence grounding,
  actionability, feasibility, internal coherence, distinctness, and constraint
  compliance;
- decision dimensions: expected impact, effort proportionality, time to value,
  reversibility, information gain, and risk;
- traceable issues with a stable code, severity, affected fields, evidence
  references, explanation, and optional repair;
- the final `SuggestionIdea` exposes the accepted critique so result consumers
  can inspect these signals without reading provider logs.

Signals use small ordinal enums (`strong`, `adequate`, `weak`, `unknown`) and a
separate risk enum (`low`, `medium`, `high`, `unknown`). They are descriptive,
not an aggregate score. Verdict and hard-reject rules remain the sole loop
control signals.

## Design

Add frozen Pydantic models and enums to `types/suggestions.py`. Defaults are
`unknown` so older fakes and providers remain valid while new providers can
return richer data. Validate issue codes, field/reference bounds, and the
existing one-critique-per-candidate contract. Update the critic prompt to
request every dimension and require issues to be evidence-backed. Preserve
the typed packet through keep/revise handling and include it on accepted ideas
in the result envelope.

## Verification

Add offline tests for signal parsing, bounds, unknown defaults, issue
traceability, and result exposure. Assert that a low or high signal alone does
not override the explicit verdict, while existing evidence and constraint
hard-reject behavior remains unchanged.

## Research-informed guardrails

The schema follows iterative self-refinement and rubric-based evaluation
patterns: use multidimensional, evidence-linked observations instead of one
scalar judge score; keep revisions targeted; and preserve explicit uncertainty
because unguided self-correction can degrade an answer.
