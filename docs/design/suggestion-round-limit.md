# Design Doc: Suggestion Round Limit

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

Raise the suggestion agent's caller-selectable critique/revision ceiling from three to eight while
keeping two as the default. The loop already stops when the critic has no revisions; this change
adds a deterministic no-change guard so an opt-in eight-round run does not spend calls repeating an
unchanged candidate.

---

## 2. Goals & Non-Goals

### Goals

- Accept rounds one through eight everywhere the current range is validated or documented.
- Preserve the default of two and the existing one-critic-pass-per-round semantics.
- Stop a candidate when a revision is structurally unchanged.
- Add boundary and off-by-one coverage to the existing suggestion verification script.

### Non-Goals

- No category, context, critic-schema, or service-class changes in this PR.
- No automatic aggregate scoring or model-selected stopping.
- No change to token, timeout, provider, or output-envelope contracts.

---

## 3. Background & Context

`SuggestionSettings`, `SuggestionRunInput`, Click help, README text, and the service loop currently
cap rounds at three. The requested eight-round ceiling is useful for difficult suggestions, but
iterative self-correction is not uniformly beneficial: [Self-Refine](https://arxiv.org/abs/2303.17651)
finds gains from targeted feedback, while [Large Language Models Cannot Self-Correct Reasoning
Yet](https://arxiv.org/abs/2310.01798) reports degradation without reliable external feedback.

The current service returns a revision to the next critic pass even when all draft fields are
unchanged. A field-level comparison can stop that silent loop without changing the public result
shape. The default remains conservative while callers can opt into the larger ceiling.

---

## 4. Requirements

### Functional Requirements

1. Click, strict input validation, Pydantic settings, README, and round help all state and enforce
   the inclusive range `1..8`.
2. The default remains `2`.
3. A run with `rounds=8` can perform one initial generation, eight critiques, and at most seven
   revisions.
4. A revision whose meaningful candidate fields equal the previous candidate does not trigger
   another critique pass and records a warning.
5. Existing token/time limits and typed provider failures retain precedence.

### Non-Functional Requirements

- No model call is added for validation or no-change detection.
- Existing stdout/result and stderr/error contracts remain unchanged.
- All behavior is covered by the repository's offline suggestion script and canonical gate.

---

## 5. High-Level Design

Change the four existing range declarations and update the round help. Add a private comparison in
`SuggestionService` that ignores generated identity/accounting fields (`id`, `revision`, `rank`,
review text, and handoff) and compares the actual candidate content. The loop filters unchanged
revisions before carrying them into another round; it keeps already reviewed ideas and reports a
shortfall/round result exactly as it does today.

```text
[rounds 1..8]
      |
 [critic review] -- no revisions --> [finish]
      |
 [generator revision] -- unchanged --> [warn + finish candidate]
      |
 [next critic pass, bounded by 8]
```

---

## 6. Detailed Design

### 6.1 Validation and Documentation

**File(s):** `README.md`, `src/vidbyte_cli/commands/agents/suggestion/suggest.py`,
`src/vidbyte_cli/commands/agents/suggestion/request_builder.py`,
`src/vidbyte_cli/commands/agents/suggestion/prompts/rounds.md`,
`src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Keeps all caller-facing and in-process round bounds consistent.

#### Interface / API

```python
click.IntRange(1, 8)
rounds: int = Field(ge=1, le=8, default=2)
```

#### Logic / Algorithm

1. Replace every `1..3` bound with `1..8`.
2. Leave defaults, error types, and setting names unchanged.
3. Describe eight as a ceiling and two as the default in help and README.

#### Edge Cases & Error Handling

- Zero, nine, booleans, and non-integers fail before model work.
- One and eight are accepted.
- A round limit never bypasses token or timeout checks.

### 6.2 No-Change Guard

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`
**Type:** Modified

#### What it does

Prevents a generator from repeatedly returning an identical candidate under a larger round ceiling.

#### Interface / API

```python
def _same_candidate_content(self, before: SuggestionIdea, after: SuggestionIdea) -> bool: ...
```

#### Logic / Algorithm

1. Compare the candidate fields that describe the suggestion and its actions.
2. Ignore stable ID, revision, rank, review summary, and generated handoff fields.
3. Filter unchanged candidates from the next revision tuple.
4. Add one deduplicated warning to the workflow outcome.

#### Edge Cases & Error Handling

- A changed action or consideration counts as a real revision.
- A revision with only a new review summary or handoff does not count as changed.
- If all revisions are unchanged, finish without a further critic call.

---

## 7. Data Model Changes

N/A - The `rounds` field keeps its type and default; only its upper validation bound changes. No
persistent data or migration is involved.

---

## 8. API Changes

The CLI option `--rounds` changes its accepted range from `1..3` to `1..8`. No HTTP endpoint or
machine envelope changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-round-limit.md` | Record this focused PR's contract. |
| MODIFY | `README.md` | Document the new range. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/suggest.py` | Expand Click validation. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/request_builder.py` | Expand strict input validation. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/rounds.md` | Explain the ceiling and guard. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Expand Pydantic bound. |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Add no-change filtering. |
| MODIFY | `scripts/test_suggestions.py` | Verify boundaries, call counts, and unchanged revisions. |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Accept one and eight; reject zero and nine in Click, dataclass, and Pydantic.
- [Hidden Assumption] Reject `True` even though Python treats it as an integer.
- [Silent Failure] An always-revise fake receives exactly eight critiques and seven revisions.
- [Hidden Failure] A fake returns an unchanged revision and the service performs no next critique.
- [Silent Failure] A revision changing only review text or handoff is classified unchanged.
- [Hidden Assumption] A token/time limit stops an eight-round run before the round ceiling.

### Integration Tests

- Run `scripts/test_suggestions.py` with the existing fake SDK.
- Run `agents suggest run --help` and inspect the `--rounds` range and explanation.
- Run the canonical `python scripts/run_ci.py` gate.

### Manual / QA Test Cases

1. Invoke a simple run with default settings and confirm it still uses two as the displayed default.
2. Invoke with `--rounds 8` and a revision-producing provider; confirm it stops on acceptance or
   unchanged output rather than blindly making eight revisions.
3. Invoke with `--rounds 9`; confirm a typed input error occurs without provider activity.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing pinned `vidbyte-sdk` | Current project pin | Provider-backed fake/real agent calls. | No SDK change is expected. |

No new dependency or external service.

---

## 12. Rollout & Deployment

- This is the first PR in the suggestion-agent refinement stack and targets `main`.
- Rollback is a code revert; callers using one through three rounds retain their behavior.
- Later category, context, critic, and service PRs should target this branch until it merges, or be
  rebased onto its merge commit.

---

## 13. Open Questions

- [ ] Should no-change stopping become a new public stop reason? Recommendation: keep the existing
  stop reason for this focused PR and expose only a warning; the critic-signals PR can revisit this
  once richer review outcomes exist.

---

## 14. Alternatives Considered

### Alternative 1: Make Eight the Default

- What: Change the default from two to eight.
- Why rejected: It increases latency and cost for every caller and is not justified by evidence that
  unguided additional rounds help every task.

### Alternative 2: Let the Model Choose When to Stop

- What: Ask the critic or generator to decide the loop length.
- Why rejected: The Python-owned bound is deterministic, testable, and prevents provider output from
  bypassing caller limits.

### Alternative 3: Add a New Score-Based Stop Rule

- What: Stop when a model-generated quality score stops improving.
- Why rejected: A score introduces calibration and verbosity bias before the dedicated critic-signal
  contract exists.
