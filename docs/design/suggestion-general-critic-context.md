# Design Doc: Suggestion General Critic Context

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-16
**Last Updated:** 2026-09-18

> Merge note (2026-09-18): `main` added the ten-section general rubric to the
> per-candidate critique protocol after this branch was cut. The merge keeps both
> systems under prompt version `suggestions.v4`: each critic returns per-candidate
> critiques with rubric scores for traceability plus one whole-slate context block
> that the persistent generator refines against. Generator and critic prompt wording
> follows current `main`; `revision.md` is still replaced by `refinement.md`.

---

## 1. Overview

The suggestion workflow will replace its one-critique-per-candidate control protocol with one
whole-slate critic context that the persistent generator may use at its discretion. Each feedback
cycle will run a fresh independent critic, validate its evidence-linked observations, place one
rendered review primitive at the end of the generator's conversation through the Vidbyte SDK
`ContextManager`, and continue the same generator thread for a complete-slate refinement. This
keeps evidence and deterministic output validation in code while returning ownership of candidate
selection, merging, removal, and revision to the generator.

---

## 2. Goals & Non-Goals

### Goals

- Return one bounded, structured critic context for the candidate slate rather than one verdict
  for every candidate.
- Continue one generator SDK agent and native thread across initial generation and refinement
  turns.
- Place the latest critic context at `END_OF_CONVERSATION` so it follows the current refinement
  request and remains the most recent model input.
- Let the generator keep, revise, merge, remove, reorder, or add candidates while preserving
  stable identifiers for candidates it carries forward.
- Preserve evidence validation, category validation, caller prohibitions, exact-title
  deduplication, horizon filtering, count limits, ranking, and deterministic execution handoffs.
- Expose critic contexts once at the run level instead of copying review metadata into each idea.
- Rewrite generator, critic, and refinement prompts in the established suggestion-agent diction
  and section style.
- Keep `--rounds` as a caller-owned count of complete critic-to-generator feedback cycles.

### Non-Goals

- No new CLI option, provider, model override, command, remote API route, or paid admission flow.
- No SDK repository change or SDK dependency revision; the pinned SDK already provides
  `ContextWindowPlacement.END_OF_CONVERSATION`.
- No model-selected stopping rule; Python still computes the loop count and may stop early only
  when the full slate is unchanged or empty.
- No semantic duplicate classifier in deterministic code.
- No change to the final execution handoff's authority, evidence embedding, or rendering.
- No new test file; the existing offline suggestion verification script will be updated with the
  new contract and remains part of canonical CI.

---

## 3. Background & Context

Current `main` constructs a fresh generator for initial generation and another fresh generator
for each targeted revision. The critic returns `SuggestionCritiqueArtifact`, which contains
exactly one `SuggestionCritique` per candidate. `SuggestionService._review` then interprets
verdict, confidence, evidence, constraint, duplicate, repair, and preservation fields as control
instructions: candidates are banked, queued for revision, or dropped before the generator sees
the next turn. Accepted ideas retain their own critique packet.

That shape prevents the generator from weighing review signal across the slate and makes a critic
decision authoritative even when the generator could reconcile it better. It also contradicts the
recorded future direction from PR #78: stop mapping the critic to individual ideas and append one
general handoff through the SDK context manager. The current CLI SDK pin already contains managed
context placements and persistent native thread continuation. The implementation therefore stays
inside `vidbyte-cli`, preserves the lazy SDK import boundary in `sdk.py`, and builds on current
`main` rather than the open PR #78 service split or conflicted PR #79 prompt branch.

The repository's prompt guidance requires model-facing prose to live in packaged Markdown,
requires structured stage outputs to be validated again in code where schemas cannot enforce
cross-record relationships, and requires a multi-turn stage to use one schema and one thread.
Prompt sections must each have one purpose and stay inside the C003 six-to-eight-sentence band.
The canonical verification command is `python scripts/run_ci.py` after installing `.[dev]`.

---

## 4. Requirements

### Functional Requirements

1. Initial non-extra-compute generation and every refinement must use the same generator agent
   object and provider-confirmed thread identifier.
2. Every feedback cycle must construct a fresh critic agent with its own context manager.
3. The critic must return one `SuggestionCriticContext` containing an overall assessment,
   strengths, bounded observations, coverage gaps, and uncertainties.
4. An observation may refer to zero, one, or several candidate IDs and context evidence refs.
5. Code must reject any critic candidate ID or evidence ref absent from the reviewed slate or
   supplied context.
6. The SDK adapter must place a replaceable `SuggestionCriticContextPrimitive` at
   `END_OF_CONVERSATION` under one stable primitive ID.
7. The generator must receive the critic context as advisory signal and return one complete
   replacement slate using the unchanged `SuggestionCandidateBatch` schema.
8. Existing candidates returned by the generator must preserve their assigned IDs; new candidates
   must omit the ID so code can assign the next stable run-local ID.
9. Code must reject duplicate IDs and non-null IDs that were not present in the preceding slate.
10. A retained candidate's revision must increment only when its meaningful draft content changes.
11. A semantically unchanged full slate must be retained and end the loop successfully instead of
    being dropped.
12. `--rounds N` must perform at most N complete critic-to-generator feedback cycles, and the
    workflow must never stop after producing feedback the generator did not receive.
13. Budget or timeout exhaustion after generation must return the latest generator-owned slate
    through the existing deterministic finalization boundary.
14. Extra compute must remain an initial per-category fan-out; its merged pool must seed one
    persistent coordinator generator for all feedback cycles.
15. Final ideas must omit per-candidate critique and review-summary fields.
16. `SuggestionResult` must expose the ordered run-level critic context history and use prompt
    version `suggestions.v3`.
17. The final execution handoff must continue to embed bounded evidence and carry no execution
    authority.
18. Generator and critic prompts must follow the existing suggestion prompt vocabulary, sentence
    rhythm, XML section names, and model-facing distinctions between evidence, assumptions,
    prohibitions, private reasoning, and structured output.
19. The obsolete revision system prompt must be replaced by a refinement turn prompt; the
    persistent generator must keep the generator system prompt for every turn.
20. The built wheel must contain the new refinement prompt and must no longer require the deleted
    revision prompt.

### Non-Functional Requirements

- The generator and critic remain explicitly read-only with deny-all approval at both SDK thread
  and turn settings.
- The SDK remains lazily imported only from `services/suggestions/sdk.py`, preserving offline
  command help when the integration is unavailable.
- Critic output is bounded to twelve strengths, twenty observations, twelve coverage gaps, and
  twelve uncertainties; each observation is bounded to thirty candidate IDs and twelve evidence
  refs.
- Context snapshots, attachments, provider errors, schema errors, token accounting, and timeout
  behavior retain their existing security and reliability boundaries.
- Results remain the only stdout content; no new progress or diagnostic output is introduced.
- All modified Python methods use one-line signatures and immediate intent comments, while other
  comments follow the repository's restrained style.
- `python scripts/run_ci.py` must pass locally and in every required pull-request matrix job.

---

## 5. High-Level Design

`SuggestionService` will own one persistent generator session and a succession of fresh critic
calls. The initial generator call produces a candidate batch, after which code assigns stable
idea IDs. Each configured cycle projects the latest ideas into a critic-only stage context, asks a
fresh critic for one whole-slate context, validates all references, appends a rendered primitive to
the persistent generator's end-of-conversation placement, and asks that same generator for the
next complete slate.

The generator's structured output remains `SuggestionCandidateBatch`, so one schema can serve its
entire native thread. Code reconciles the replacement slate against the previous slate: known IDs
retain identity, changed candidates increment revision, unchanged candidates retain revision, and
ID-less candidates receive the next available ID. The latest slate then passes through the
existing deterministic category, evidence, rejected-direction, horizon, deduplication, handoff,
and ranking steps.

The critic output becomes `SuggestionCriticContext`. It keeps evidence-linked observations and
whole-slate strengths, gaps, risks, and uncertainty, but removes verdicts and field-level repair
orders. A companion primitive renders the entire artifact as one Markdown block at a stable
context ID. The latest primitive replaces the previous manager entry; earlier feedback remains
available through the native generator thread history and the result's ordered context history.

```text
initial generator session -> assign stable IDs -> fresh critic
          ^                                      |
          |                                      v
          +-- same thread <- END_OF_CONVERSATION review context
                    |
                    v
          complete replacement slate -> deterministic finalization -> result
```

---

## 6. Detailed Design

### 6.1 Suggestion contracts and context primitives

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Replaces the candidate-level critic protocol with one slate-level review contract and removes
candidate fields that represented controller-owned review state.

#### Interface / API

```python
class CriticObservationKind(StrEnum): ...


class SuggestionCriticObservation(BaseModel):
    kind: CriticObservationKind
    candidate_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    signal: str
    implication: str
    possible_response: str


class SuggestionCriticContext(BaseModel):
    overall_assessment: str
    strengths_to_preserve: tuple[str, ...]
    observations: tuple[SuggestionCriticObservation, ...]
    coverage_gaps: tuple[str, ...]
    uncertainties: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SuggestionCriticContextPrimitive:
    context: SuggestionCriticContext
    primitive_id: str = "suggestion-critic:latest"
    primitive_frozen: bool = False

    def to_context_text(self) -> str: ...
```

`SuggestionAgentContext` retains evidence, category guidance, and optional candidates but removes
the per-candidate critiques tuple. `SuggestionIdea` removes `review_summary` and `critique`.
`SuggestionResult` adds `critic_contexts: tuple[SuggestionCriticContext, ...]` and defaults to
prompt version `suggestions.v3`.

#### Logic / Algorithm

1. Render the critic artifact as one titled Markdown block with sections for the assessment,
   strengths, observations, coverage gaps, and uncertainties.
2. Include candidate IDs and evidence refs only when an observation supplies them.
3. Keep the primitive replaceable and give it a stable ID so the context manager holds only the
   latest memo.
4. Project an idea back to `SuggestionDraft` by removing only CLI-owned identity, revision, rank,
   and handoff data.

#### Edge Cases & Error Handling

- Empty optional collections render an explicit `none supplied` line so absence is visible.
- Pydantic rejects extra fields, oversized collections, blank prose, and invalid observation
  kinds before the next generator turn.
- Reference membership cannot be expressed in JSON Schema and is validated in the service.

### 6.2 SDK generator session and context placement

**File(s):** `src/vidbyte_cli/services/suggestions/sdk.py`
**Type:** Modified

#### What it does

Adds a local session wrapper that keeps the generator agent and its SDK context manager together,
verifies stable native thread identity, and places critic context at the SDK's exact
end-of-conversation location.

#### Interface / API

```python
@dataclass(slots=True)
class SuggestionAgentSession:
    agent: SuggestionAgent
    context_manager: Any
    thread_id: str = ""

    def verify_thread(self) -> None: ...


class SuggestionSdk:
    def agent_session(self, request: SuggestionAgentSettingsInput) -> SuggestionAgentSession: ...
    def place_critic_context(
        self, session: SuggestionAgentSession, context: SuggestionCriticContextPrimitive
    ) -> None: ...
```

#### Logic / Algorithm

1. Load `ContextWindowPlacement` beside `ContextManager` through the existing lazy binding map.
2. Construct one generator session from the same validated settings used for ordinary agents.
3. After every successful generator turn, require a nonempty thread ID and require later turns to
   preserve it.
4. Upsert the latest critic primitive with `END_OF_CONVERSATION` placement.

#### Edge Cases & Error Handling

- Missing, blank, or changed generator thread identity raises before another model turn begins.
- Wrong session or critic primitive types fail at the local SDK boundary.
- Critic and extra-compute agents continue to use fresh context managers and ordinary agent
  construction.

### 6.3 Persistent feedback-cycle orchestration

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`
**Type:** Modified

#### What it does

Replaces controller-directed keep/revise/reject handling with persistent generator refinement over
whole-slate critic context.

#### Interface / API

```python
class SuggestionService:
    async def _run(self, request: SuggestionRequest, sdk: Any) -> _WorkflowOutcome: ...
    async def _critique(self, state: _RunState, ideas: Ideas) -> SuggestionCriticContext: ...
    async def _call_session(
        self, state: _RunState, session: SuggestionAgentSession, prompt: str, phase: str
    ) -> SuggestionCandidateBatch: ...
```

#### Logic / Algorithm

1. Build the initial slate through one persistent generator session, or through existing
   extra-compute fan-out followed by a coordinator session seeded with those candidates.
2. Assign stable IDs to the initial drafts and retain the next available numeric ID.
3. For each configured feedback cycle, run a fresh critic over the current slate.
4. Validate every candidate and evidence reference in the returned context.
5. Append the review primitive, continue the same generator session with the refinement turn, and
   reconcile its complete batch against the current ideas.
6. If the reconciled slate is empty, return a count shortfall; if it is semantically unchanged,
   retain it and complete early.
7. After all cycles, finalize the latest slate and return completed or count-shortfall status.
8. If time or token limits stop later work, finalize the most recent generator-owned slate and
   return the corresponding stop reason.

#### Edge Cases & Error Handling

- Duplicate returned IDs, invented non-null IDs, critic references to absent candidates, and
  critic evidence refs outside the manifest are provider failures through the existing service
  error translation.
- New candidates must omit `idea_id`; code assigns IDs monotonically and never recycles a dropped
  ID.
- Reordering alone is meaningful generator discretion and is preserved.
- A content-identical slate in identical order is convergence, not refusal.
- Attachments continue to reach every model turn through the existing typed input builder.

### 6.4 Extra-compute coordination

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`
**Type:** Modified

#### What it does

Keeps category fan-out as an initial exploration topology while giving one coordinator generator
ownership of all later feedback cycles.

#### Interface / API

N/A - the public `ExtraComputeService.generate` contract remains unchanged.

#### Logic / Algorithm

1. Run existing focused category generators concurrently.
2. Assign stable IDs to the merged bounded pool.
3. Create the coordinator generator with a stage context that includes the merged candidates.
4. After its first refinement turn, replace the seeded stage context with evidence and category
   guidance only so stale candidates are not repeated in later system context.

#### Edge Cases & Error Handling

- An empty merged pool returns the existing count-shortfall result without constructing a critic.
- Fan-out failures retain their existing behavior; this change does not add partial-branch policy.

### 6.5 Deterministic selection wording

**File(s):** `src/vidbyte_cli/services/suggestions/selection.py`
**Type:** Modified

#### What it does

Updates documentation to describe validation over generator-owned candidates rather than
critic-approved candidates. Selection behavior remains unchanged.

#### Interface / API

N/A - no signature or runtime behavior changes.

#### Logic / Algorithm

N/A - existing deterministic filters and rank assignment remain authoritative.

#### Edge Cases & Error Handling

N/A - existing behavior is unchanged.

### 6.6 Model prompts and prompt loader

**File(s):**
`src/vidbyte_cli/services/suggestions/prompts/generator.md`,
`src/vidbyte_cli/services/suggestions/prompts/critic.md`,
`src/vidbyte_cli/services/suggestions/prompts/refinement.md`,
`src/vidbyte_cli/services/suggestions/prompts/revision.md`,
`src/vidbyte_cli/services/suggestions/prompts/library.py`
**Type:** Modified, New file, and Deleted

#### What it does

Makes the critic a whole-slate signal producer and makes refinement an ordinary turn on the
persistent generator system identity.

#### Interface / API

```python
class SuggestionPrompts:
    def generator_system(self) -> str: ...
    def critic_system(self) -> str: ...
    def generator_turn(self, goal: str, count: int) -> str: ...
    def critic_turn(self, goal: str, candidate_ids: str) -> str: ...
    def refinement_turn(self, goal: str, count: int) -> str: ...
```

#### Logic / Algorithm

1. Model generator and critic wording on the current suggestion prompt family and the accepted
   altitude guidance from PR #79: Identity, Goal, private Algorithm, Prohibitions, and Output.
2. Tell the critic to return one evidence-linked view of the slate without deciding which
   candidates survive.
3. Tell the generator that review context is advisory and that it owns the complete replacement
   slate.
4. Remove unresolved `{{categories}}` and `{{context}}` placeholders because the context manager
   already supplies both values.
5. Load a short refinement turn prompt while retaining the generator system prompt and schema.
6. Delete the obsolete revision system prompt and loader method.

#### Edge Cases & Error Handling

- Every paired XML section remains between six and eight complete sentences for C003.
- Collection bounds omitted by provider grammars are restated in critic output prose.
- The refinement prompt requires retained IDs and reserves missing IDs for genuinely new ideas.

### 6.7 Caller-facing round documentation

**File(s):**
`src/vidbyte_cli/commands/agents/suggestion/prompts/rounds.md`,
`README.md`,
`src/vidbyte_cli/services/suggestions/README.md`
**Type:** Modified

#### What it does

Documents that a round is now a complete critic-to-generator feedback cycle and that review is
run-level advisory context.

#### Interface / API

N/A - the accepted range, option name, and default stay unchanged.

#### Logic / Algorithm

1. Keep the one-through-eight range and default of two.
2. Explain that each cycle adds one critic call and one continued generator turn.
3. Explain unchanged-slate early completion and caller-owned time/token limits.

#### Edge Cases & Error Handling

- Help continues to satisfy the repository's long-form caller-facing prose rules.
- Existing command invocations remain valid but may use one additional model call because every
  produced review is now consumed by the generator.

### 6.8 Verification and packaged assets

**File(s):** `scripts/test_suggestions.py`, `scripts/run_ci.py`
**Type:** Modified

#### What it does

Updates the existing offline verification and wheel manifest for the new context contract without
adding a new test file.

#### Interface / API

N/A - these are repository verification entry points.

#### Logic / Algorithm

1. Make the fake SDK expose reusable sessions, mutable fake context managers, and stable thread
   IDs.
2. Verify one critic context may span several candidates and reject invented references.
3. Verify the same generator agent handles initial and refinement turns.
4. Verify the critic primitive uses `END_OF_CONVERSATION` and renders after current input.
5. Verify unchanged slates survive and stop early, while changed, added, removed, and reordered
   candidates reconcile correctly.
6. Verify final review history is run-level and ideas carry no per-candidate critique fields.
7. Replace the wheel's expected revision prompt with the refinement prompt.
8. Run the complete canonical gate after focused iteration.

#### Edge Cases & Error Handling

- Verification remains offline and starts no provider process.
- Existing attachment, dry-run, context-limit, handoff, CLI, category, and packaging checks remain
  active.

---

## 7. Data Model Changes

### 7.1 Critic observation and context

**Change type:** New

```python
class CriticObservationKind(StrEnum):
    STRENGTH = "strength"
    EVIDENCE = "evidence"
    CONSTRAINT = "constraint"
    REDUNDANCY = "redundancy"
    COVERAGE = "coverage"
    FEASIBILITY = "feasibility"
    ACTIONABILITY = "actionability"
    TRADEOFF = "tradeoff"
    RISK = "risk"


class SuggestionCriticObservation(BaseModel): ...


class SuggestionCriticContext(BaseModel): ...
```

**Migration strategy:**

- Forward migration: providers return one whole-slate artifact, and results expose it under
  `critic_contexts` with prompt version `suggestions.v3`.
- Rollback plan: revert the feature commits to restore `SuggestionCritiqueArtifact` and the
  candidate-level review loop.

### 7.2 Candidate-level critique contracts

**Change type:** Deleted

`CritiqueVerdict`, `CritiqueConfidence`, `CritiqueEvidenceCheck`, `CritiqueConstraint`,
`CritiqueSignalLevel`, `CritiqueRiskLevel`, `CritiqueIssueSeverity`,
`SuggestionCritiqueSignals`, `SuggestionCritiqueIssue`, `SuggestionCritique`, and
`SuggestionCritiqueArtifact` are removed because no controller consumes per-candidate decisions.

**Migration strategy:**

- Forward migration: equivalent useful signal becomes a typed observation with optional many-to-
  many candidate and evidence references.
- Rollback plan: revert the schema and service commits together; mixed old/new contracts are not
  supported.

### 7.3 Suggestion idea and result

**Change type:** Modified

`SuggestionIdea.review_summary` and `SuggestionIdea.critique` are removed.
`SuggestionResult.critic_contexts` is added, and the default prompt version becomes
`suggestions.v3`.

**Migration strategy:**

- Forward migration: machine consumers read review information once from `critic_contexts` rather
  than from each idea. The enclosing `suggestions.result` kind remains unchanged.
- Rollback plan: revert the result model and renderer-neutral service construction together.

---

## 8. API Changes

N/A - no remote HTTP endpoint changes. The local `agents suggest run` command keeps the same
arguments, but its machine-readable `suggestions.result` data removes per-idea `review_summary`
and `critique`, adds run-level `critic_contexts`, and advances `prompt_version` to
`suggestions.v3`. This is an intentional alpha contract change and is described in the README.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-general-critic-context.md` | Source-of-truth design |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/refinement.md` | Persistent generator refinement turn |
| MODIFY | `README.md` | Document run-level review and cycle semantics |
| MODIFY | `scripts/run_ci.py` | Verify the new packaged prompt asset |
| MODIFY | `scripts/test_suggestions.py` | Update existing offline contract verification |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/rounds.md` | Explain complete feedback cycles |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/count.md` | Describe whole-slate pool selection |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/extra_compute.md` | Describe refinement after fan-out |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/max_total_tokens.md` | Describe refinement token accounting |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/max_output_tokens.md` | Describe refinement output limits |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/run.md` | Describe critic signal use |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/prompts/timeout.md` | Describe refinement timeout accounting |
| MODIFY | `src/vidbyte_cli/services/suggestions/README.md` | Update service topology summary |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/critic.md` | Produce one whole-slate signal context |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/generator.md` | Give the persistent generator slate ownership |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/library.py` | Load refinement turns and remove revision system API |
| DELETE | `src/vidbyte_cli/services/suggestions/prompts/revision.md` | Replaced by persistent-thread refinement turn |
| MODIFY | `src/vidbyte_cli/services/suggestions/sdk.py` | Retain generator session and place critic context |
| MODIFY | `src/vidbyte_cli/services/suggestions/selection.py` | Align documentation with generator-owned results |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Implement feedback cycles and slate reconciliation |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Replace per-candidate critique with run-level context |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte-sdk[codex]` | Git revision `6f9f84a257036e65bab9595d3c34e8a98cdcd96e` | Persistent Codex thread and context placement | No pin change; API availability verified locally |
| OpenAI Codex provider | Existing local SDK integration | Generator and critic model turns | Two model calls per configured feedback cycle |

---

## 11. Rollout & Deployment

- Feature flags: N/A - the workflow changes when the updated CLI wheel is installed.
- Breaking change: machine-readable review data moves from each idea to the result-level
  `critic_contexts` collection, and `prompt_version` advances to `suggestions.v3`.
- Deployment order: one CLI artifact; no backend or SDK deployment dependency.
- Rollback: revert the implementation commits together and republish the prior CLI artifact.
- Pull request: target `main`; the branch deliberately does not depend on open PR #78 or #79.
- Verification: install `.[dev]`, run `python scripts/run_ci.py`, push, create a draft PR, and wait
  for all four required OS/Python jobs to pass.

---

## 12. Open Questions

N/A - the user accepted persistent generator ownership, whole-slate critic context, and SDK
context-manager placement. Round semantics, result exposure, stable ID behavior, extra-compute
coordination, and the `main` branch base are resolved in this design.

---

## 13. Alternatives Considered

### Alternative 1: Keep verdicts as hidden controller fields

- What: return a general memo while retaining keep/revise/reject fields for deterministic routing.
- Why rejected: the critic would still own candidate survival, which defeats generator discretion
  and preserves two competing sources of truth.

### Alternative 2: Put critic text in the refinement prompt

- What: concatenate the memo onto the user prompt without the SDK context manager.
- Why rejected: it loses typed context identity and placement, duplicates prompt assembly logic,
  and does not establish the requested end-of-context contract.

### Alternative 3: Create a fresh generator for each refinement

- What: keep current cold revision agents but pass one general memo.
- Why rejected: the new agent cannot see its own earlier slate or reasoning, while the SDK already
  supports one schema and one resumed native thread for multi-turn stages.

### Alternative 4: End with a final critic approval turn

- What: preserve current final acceptance by running a critic after the last generator turn.
- Why rejected: it produces feedback the generator never receives and reintroduces critic authority
  over the terminal slate.

### Alternative 5: Base on open PR #78 or #79

- What: stack the feature on the unmerged service-layering or prompt-resolution branches.
- Why rejected: the user asked for current `main`; PR #78 has a non-main base and PR #79 is dirty.
  A self-contained main-based change avoids importing unrelated stacked work and makes conflicts
  explicit to those PRs rather than hiding them in this feature.
