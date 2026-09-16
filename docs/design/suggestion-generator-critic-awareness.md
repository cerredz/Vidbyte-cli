# Design Doc: Suggestion Generator Critic Awareness

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-16
**Last Updated:** 2026-09-16

---

## 1. Overview

The suggestion generator writes its candidate slate with no knowledge that an independent critic
reviews every candidate it produces, that some verdicts are fatal while others are repairable, or
that its own next turn may be a narrow repair turn driven by that critic's instructions. This
change adds one `<Review>` section to `prompts/generator.md` explaining the generator's place in
the generate to critique to revise loop and how to treat the feedback it will receive. It is a
prompt-only change: no Python, no schema, no command surface, and no loop behavior moves.

---

## 2. Goals & Non-Goals

### Goals
- Tell the generator, in its system prompt, that an independent critic reviews every candidate.
- Explain what the critic can and cannot see, so quality is written onto the page rather than left
  in unstated deliberation.
- Explain which critic outcomes are fatal, which are repairable, and which bank a candidate.
- Explain how to treat a fix instruction when the generator is called back for a repair turn.
- Keep the addition to roughly one to two paragraphs, in the section style `generator.md` uses.

### Non-Goals
- No change to `critic.md` or `revision.md`; both already describe the loop from their own side.
- No change to `service.py`, `selection.py`, `sdk.py`, or any schema in `types/suggestions.py`.
- No new placeholder token; the section is static prose that needs no value from `library.py`.
- No change to verdict semantics, round limits, pool sizing, or the unchanged-revision cut.
- No rewrite of the existing `<Identity>`, `<Goal>`, `<Algorithm>`, or `<Output>` sections.

---

## 3. Background & Context

`services/suggestions/` runs a real SDK-backed loop on `origin/main`. `SuggestionService._run`
generates a candidate pool, then for up to `settings.rounds` rounds (`ge=1, le=8, default=2`) calls
an independent critic, splits the result into kept and to-revise candidates, and calls a revision
turn for the latter. The three prompts are packaged Markdown: `generator.md`, `critic.md`, and
`revision.md`.

Two of those three prompts already state the relationship. `critic.md` opens by saying it receives
the candidate artifact "but no private generator deliberation", and `revision.md` says to "treat
the critic as a repair instruction, not as permission to execute work". `generator.md` says
nothing about either. It describes how to draft a slate and then stops, as though its output were
terminal. The generator is therefore the only participant in the loop that does not know the loop
exists.

That gap has consequences the code makes concrete. `_review` drops a candidate outright when the
critic reports a constraint hit, contradicted evidence, or a confident rejection, and routes it to
repair when the verdict is revise, evidence is merely missing, or the rejection is low confidence.
`_run` then compares each repaired candidate against its original with `_same_candidate_content`
and deletes any that came back semantically unchanged, warning "Stopped N unchanged suggestion
revision(s) before another critique." A generator that does not know these rules cannot optimize
for them: it has no reason to prefer a labelled assumption over an unsupported factual claim, and
no reason to treat a repair turn as obligatory rather than optional.

The constraint on the work is the repository's prompt convention, recorded in the workspace field
guide under "Agent Stage Prompts": model-facing text lives in its own Markdown file, sections are
explicit, and no `.py` file may contain a sentence addressed to a model. The suggestions family
uses capitalized single-word sections (`<Identity>`, `<Goal>`, `<Algorithm>`, `<Output>`) with one
sentence per line, and `revision.md` already proves the section set varies per stage.

---

## 4. Requirements

### Functional Requirements
1. `generator.md` gains exactly one new section explaining the critic relationship.
2. The section states that an independent critic reviews every candidate the generator returns.
3. The section states that the critic sees the goal, the bounded context, and the candidate
   artifact, and never sees the generator's private deliberation.
4. The section distinguishes fatal outcomes (constraint hit, contradicted evidence, confident
   rejection, duplicate) from repairable ones (revise, missing evidence, low-confidence rejection).
5. The section states that a kept candidate is banked and does not need re-defending.
6. The section states that a repair turn must make a real field-level change, because an unchanged
   candidate is dropped from the run.
7. The section states that rounds are finite, so a defect should be fixed on first response rather
   than deferred.
8. The section states that a smaller, better-supported slate is preferred over filler, since the
   critic removes weak candidates anyway.
9. The section reframes critique as the mechanism that gets a candidate to the caller, not as an
   adversary to argue with.
10. The addition introduces no new `{{token}}` placeholder.
11. Every other line of `generator.md` is unchanged.

### Non-Functional Requirements
- **Packaging:** `generator.md` is already covered by the `services/suggestions/prompts/*.md` glob
  in `[tool.setuptools.package-data]`; no packaging change is required, and the built wheel must
  still carry the file.
- **Style:** one sentence per line, matching the four existing sections.
- **Observability:** N/A - prompt text emits no telemetry of its own; loop warnings already report
  unchanged revisions.
- **Performance:** the section adds roughly 300 tokens to each generation and repair turn, which is
  immaterial against the candidate pool the same turn returns.
- **Reliability:** static prose cannot fail to render; a missing placeholder is impossible because
  none is added.

---

## 5. High-Level Design

One file changes. `prompts/generator.md` gains a `<Review>` section placed after `<Algorithm>` and
before `<Output>`. That position follows the file's existing progression: who you are, what
property the output must have, how to draft it, what happens to it afterwards, and finally the
response contract. Putting it before `<Output>` also means the last thing the generator reads
before the turn placeholders is still the output contract itself.

The section is written as two six-line stanzas separated by a blank line. That satisfies the
request for one to two paragraphs of content while preserving the six-lines-per-section rhythm
every other section in the suggestions family uses. The first stanza covers the relationship and
what the critic can see; the second covers what to do with the feedback that comes back.

Nothing reads the file except `SuggestionPrompts._read`, which strips and caches the text, so a
new static section flows into both `generator_system()` call sites with no code change.

```
_generate  --> generator.md <Review> tells it review is coming
   |
   v
_critique  --> critic.md  --> per-candidate verdicts
   |
   v
_review    --> kept (banked) | revisions (repairable) | dropped (fatal)
   |
   v
_revise    --> revision.md on the generator role, then the unchanged-content cut
```

---

## 6. Detailed Design

### 6.1 Suggestion generator prompt

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/generator.md`
**Type:** Modified

#### What it does
Supplies the system prompt for the generation turn and, through `generator_system()`, the role
under which the extra-compute generation path also runs.

#### Interface / API
No Python interface changes. The file continues to be read by:

```python
def generator_system(self) -> str:
    # System prompt for generation and revision turns.
    return self._read("generator")
```

#### Logic / Algorithm
1. Insert a `<Review>` section between the closing `</Algorithm>` tag and the opening `<Output>`
   tag, separated by one blank line on each side, matching existing spacing.
2. Stanza one states the relationship: an independent critic reviews every candidate; it sees the
   goal, context, and candidate artifact but no private reasoning; unstated justification is
   invisible; a fabricated or unsupported reference is caught by the verdict; a labelled assumption
   is repairable where a false claim of evidence is not; and review is what carries a candidate to
   the caller.
3. Stanza two states the response to feedback: a keep is banked and needs no re-defending; a revise
   or missing-evidence verdict returns the candidate for a narrow field-level repair; a returned
   candidate that is materially unchanged is removed from the run; the fix instruction is a repair
   order rather than an opening position; rounds are finite so defects are fixed on first response;
   and a shorter well-supported slate beats filler the critic will cut.
4. Leave every other byte of the file unchanged.

#### Edge Cases & Error Handling
- **Loop never reaches a repair pass (`--rounds 1`):** the section stays accurate, because round one
  still critiques; only the repair turn is skipped. It describes what the critic does, not a
  guarantee that a repair turn occurs.
- **Stale editable install:** `_read` resolves from the installed package, so an out-of-date install
  could serve an old copy; this is existing behavior for every prompt and is not introduced here.
- **Revision turn:** the repair turn runs under `revision_system()`, not this file, so the new
  section does not conflict with `revision.md`'s narrower algorithm; it prepares the generator for
  that turn rather than duplicating its instructions.
- **Contradiction risk:** the section asserts nothing the code does not enforce, so it cannot drift
  from behavior without a corresponding change in `_review` or `_same_candidate_content`.

---

## 7. Data Model Changes

N/A - no schema, collection, or typed payload changes. `SuggestionCritique`,
`SuggestionCandidateBatch`, and `SuggestionIdea` are untouched.

---

## 8. API Changes

N/A - no HTTP route and no CLI command surface changes. `agents suggest run` keeps every flag and
every output envelope it has today.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-generator-critic-awareness.md` | This design doc |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/generator.md` | Add the `<Review>` section |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | - | No dependency is added, removed, or upgraded | None |

---

## 11. Rollout & Deployment

- **Feature flags:** none; prompt text ships with the wheel and takes effect on the next run.
- **Breaking change:** no. The section adds guidance only and changes no contract a caller relies
  on; output remains the same structured `SuggestionCandidateBatch`.
- **Deployment order:** single repository, single artifact.
- **Rollback:** revert the one commit touching `generator.md`.
- **Canonical gate:** `python scripts/run_ci.py` from the repository root, plus `python lint/run.py`.

---

## 12. Open Questions

- [ ] Should `revision.md` gain a matching backward reference to the generator turn, or is the
      current one-way framing correct? Left out of scope deliberately.
- [ ] `generator_turn` passes a `revision=` value while `generator.md` contains no `{{revision}}`
      token, and the file also holds `{{categories}}` and `{{context}}` tokens that `generator_turn`
      never fills, leaving them literal unless the context primitive supplies them. Pre-existing on
      `origin/main` and untouched here; worth a separate look.

---

## 13. Alternatives Considered

### Alternative 1: Extend `<Identity>` instead of adding a section
- What: append the critic relationship to the existing six identity lines.
- Why rejected: the field guide requires sections that do not overlap, and identity is read as
  *who you are* rather than *what happens to your output*. It would also push `<Identity>` past the
  six-line rhythm every section in the family holds.

### Alternative 2: Put the guidance in the turn prompt rather than the system prompt
- What: add the text to the trailing placeholder block so it rides each turn.
- Why rejected: the relationship is a standing fact about the generator's role, not per-turn data,
  and the system prompt is where the sibling repair role already keeps its standing facts.

### Alternative 3: Write it as literal prose paragraphs
- What: two flowing paragraphs instead of one-sentence-per-line stanzas.
- Why rejected: every section in all three suggestion prompts is one sentence per line; a prose
  block would be the only exception, and the field guide treats prompt text as reviewed prose where
  consistency is the point. Two stanzas preserve the paragraph shape the request asked for.

### Alternative 4: Also add the section to `revision.md`
- What: mirror the guidance into the repair prompt.
- Why rejected: `revision.md` already states the critic relationship from the repairing side in its
  identity and output sections; repeating it would be the overlap the field guide warns about.
