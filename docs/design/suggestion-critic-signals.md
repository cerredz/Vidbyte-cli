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

Signals use a seven-level ordinal enum (`exceptional`, `strong`, `adequate`,
`marginal`, `weak`, `absent`, `unknown`), risk uses a six-level enum
(`negligible`, `low`, `moderate`, `high`, `critical`, `unknown`), and issue
severity uses a seven-level enum (`blocker`, `critical`, `major`, `moderate`,
`minor`, `note`, `info`). They are descriptive, not an aggregate score.
Verdict and hard-reject rules remain the sole loop control signals.

## Design

Add frozen Pydantic models and enums to `types/suggestions.py`. Every new
field carries a multi-sentence `Field(description=...)` because the critic
agent receives the Pydantic model as its Codex `output_schema`: descriptions
become the wire schema the model reads, so they — not prompt prose — are the
enforcement layer for what each dimension means and when to use `unknown`.
Defaults are `unknown` so older fakes and providers remain valid while new
providers can return richer data. Validate issue codes, field/reference
bounds, and the existing one-critique-per-candidate contract. Keep the critic
prompt to a high-level output summary plus count bounds (`exactly one`
critique per candidate, `up to twelve` issues), which the wire schema cannot
enforce. Preserve the typed packet through keep/revise handling and include
it on accepted ideas in the result envelope.

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
