# Design Doc: Suggestion Agent

**Status:** Implemented in the replacement for PR #50
**Scope:** CLI-local next-action generation with provider-backed generator and critic agents

## Overview

`vidbyte-cli agents suggest run` accepts one goal, optional caller-supplied context, and
generation settings. It returns ranked ideas with structured evidence, decision points,
eight-to-ten considerations, completion checks, and deterministic handoffs. The command
never launches the proposed work and never infers authority from a suggestion.

The public command family is:

- `run` — build, critique, revise, and rank suggestions through the configured provider.
- `categories --view-all` — list all 31 high-level category summaries without a model.
- `categories --view ID` — inspect one category's authored description and considerations.
- `handoff --input result.json --idea idea-003` — extract one saved handoff without a model.

## Contracts

Run input is argv-driven. The command does not accept a JSON request file or stdin document
for the run verb, because one strict `SuggestionRunInput` dataclass and one strict
`SuggestionSettings` model own defaults, ranges, categories, provider choices, and feature
flags. Context values use one canonical destination name each, and all explicit file inputs use
the repeated `--files` option. The generator uses the provider default; `--critic-model` is an
optional override for independent review only. The handoff verb retains `--input` because it
reads a previously emitted result artifact.

`--count` defaults to 5 and accepts 2–15. `--rounds` defaults to 2 and accepts 1–3.
`--extra-compute` fans out one fresh generator context for each selected category and combines
the stable typed results before the independent critic runs. `--max-output-tokens` accepts up
to 5,000,000, `--max-total-tokens` accepts up to 20,000,000, and timeout accepts up to 86,400
seconds. The final slate may be short when review rejects weak, duplicate, unsupported, or
forbidden candidates.

Context is explicit and bounded. Text, Markdown, and documented JSON files are accepted only
when named by the caller, with a 5,000,000-character per-item and aggregate body cap. The
manifest records stable references, source identity, bounded character count, digest, and
included/truncated/omitted status. Contradictory completed and in-progress statements remain
visible and produce a warning. Caller content is task data and cannot override agent policy.

Every generator and critic context contains one custom `SuggestionContextPrimitive` managed by
an independent SDK `ContextManager`. It renders the goal, the exact `<Selected Categories>`
block, context records, and, for critique, the exact `<Candidate Handoffs>` block. Generator
and critic managers are never shared. Each selected category maps one-to-one to its authored
Markdown prompt asset, and no category is inferred from a model-produced idea.

## Workflow

1. `SuggestionRequestBuilder` builds the strict request, resolves explicit context, attaches
   the selected category block, and completes all local validation before provider loading.
2. The generator returns a typed `SuggestionCandidateBatch` with a pool of up to twice the
   requested count, capped at 40. The SDK adapter creates a read-only, deny-all agent with the
   declared structured output schema.
3. The critic receives only the bounded context and candidate handoffs in a separate context
   window. It returns exactly one `SuggestionCritique` per candidate with verdict, confidence,
   evidence check, constraint hit, duplicate identifier, fix instruction, preserved fields, and
   review summary.
4. High-confidence rejects, forbidden/completed/in-progress conflicts, contradictory evidence,
   and duplicates are removed. A revise verdict, missing evidence, or low-confidence reject is
   revised only when a specific evidence-backed fix exists.
5. Revisions preserve candidate identity, apply only the critic's fix, increment revision, and
   return to critique. Kept candidates accumulate across rounds, while the last fully reviewed
   batch remains available for a shortfall or limit result.
6. Selection validates category ids and evidence refs, performs exact-title deduplication,
   suppresses caller-rejected directions, refreshes deterministic handoffs, and ranks at most
   the requested count.

Provider failures are typed and never become a false `no_suggestions` result. Dry-run, category
inspection, handoff extraction, and the offline test suite do not call a provider.

## Prompt assets

Model-facing prompts live in Markdown and are loaded with `importlib.resources` so the installed
wheel and a checkout use the same assets. Generator, critic, and revision prompts each carry
focused XML sections with six-to-eight sentences. Category prompts carry one title, a Description of
exactly two six-to-eight sentence paragraphs, a prose `Why use` rationale arguing that category
against the ones it is confused with, ten-to-fifteen `Use cases` items, and a `When not to use`
list closed by a paragraph naming the categories that fit instead. Timelines, the old generic
checklist, and the generic `Things to consider` list are intentionally absent. C003 enforces XML section depth and
C004 enforces category structure; the runtime loader does not duplicate those lint concerns.

Caller-facing help assets for dynamic text and path values use named headings for purpose,
boundaries, inputs, defaults, output, usage, examples, related commands, failures, and
authentication. Each section has six-to-eight sentences and a concrete brace-delimited command
example. C005 checks this family mechanically while leaving numeric, enum, list, and flag help
to C001. The help assets are only for the parent caller and are never added to the agent context;
the context window receives the caller's actual values and model-facing category prompts.

## File ownership

- `commands/agents/suggestion/` owns Click declarations, caller help, request construction, and
  rendering.
- `services/suggestions/` owns context assembly, category registry, SDK binding, the workflow,
  extra-compute fan-out, selection, handoff construction, and prompt loading.
- `types/suggestions.py` owns frozen, extra-forbid input, draft, critique, idea, handoff, and
  result contracts.
- `lib/errors/failures.py` owns every user-visible failure with static descriptions, traces,
  hints, and safe causes.
- `scripts/test_suggestions.py` fakes only the SDK turn and verifies the real service boundary.
- `scripts/run_ci.py` checks source gates, smoke, package data, and a clean installed wheel.

## Verification

The focused suite is:

```bash
python scripts/test_suggestions.py
python lint/run.py --rule C004
```

The canonical gate is `python scripts/run_ci.py`. Its wheel manifest checks every generator,
critic, revision, command-help, and category asset, including all 31 category files.
