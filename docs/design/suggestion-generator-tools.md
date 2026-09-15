# Design Doc: Suggestion Generator-Owned Tool Editing

**Status:** Draft  
**Author:** Codex  
**Created:** 2026-09-15  
**Last Updated:** 2026-09-15

---

## 1. Overview

Replace the suggestion service's host-side candidate revision algorithm with a generator-owned
editing pass. The critic will still return the existing typed critique artifact, but the service
will inject that artifact as bounded review data into a fresh generator system prompt. The fresh
generator will edit a run-local, typed suggestion store through add, remove, and request-more
tools. This keeps the final decision about how to repair or expand a suggestion with the generator
while keeping state, validation, permissions, and the returned result under host control.

---

## 2. Goals & Non-Goals

### Goals

- Remove the `_review`/`_revise` candidate-revision algorithm from the suggestion service.
- Preserve the existing structured critic contract and inject its validated artifact into the
  generator's system prompt as delimited data.
- Give the post-critique generator bounded tools for adding, removing, and requesting more ideas.
- Keep all mutable state local to one run and commit only a complete generator pass.
- Validate every tool mutation against the existing suggestion, category, evidence, size, and
  identity contracts.
- Preserve the existing `SuggestionResult` output shape for this PR; grouped output is a separate
  follow-up PR.
- Retain `--rounds` as the maximum number of complete critique-and-curation passes; rounds no
  longer select individual candidates or invoke a special revision algorithm.

### Non-Goals

- No semantic keep/revise/reject decision in Python.
- No new persistent store, database, network endpoint, or execution authority.
- No change to the public result grouping or result schema version.
- No change to the critic's meaning or its per-candidate response shape.
- No implementation of a hard intra-Codex token cutoff; the current SDK exposes usage after a run.

---

## 3. Background & Context

- `services/suggestions/service.py` currently interprets every critique, calls a dedicated
  revision prompt, and can repeat that process for configured rounds.
- The requested behavior is that the critique is advice for the generator, not an algorithm that
  selectively rewrites candidates in the service.
- `types/suggestions.py` already provides strict `SuggestionDraft`, `SuggestionIdea`, critique,
  handoff, and result models that can validate the store boundary.
- The SDK `main` branch at `d8483257` supports arbitrary `@tool` functions and `BaseTool`
  instances through `CodexHarnessAgentSettings.tools`, with permission policy enforcement.
- The CLI currently pins an older SDK commit, so the dependency pin must move to the merged tool
  implementation before the feature can run from an installed wheel.

---

## 4. Requirements

### Functional Requirements

1. The initial generator continues to return a typed candidate batch and seeds a run-local store.
2. The critic receives the initial store snapshot and returns exactly one validated critique for
   every candidate identifier.
3. The service serializes only the validated critique artifact into a delimited generator system
   prompt block; raw provider text is never injected.
4. A fresh post-critique generator receives the current snapshot and the critique block and has
   access to exactly three run-local tools: `add_suggestion`, `remove_suggestion`, and
   `more_suggestions`.
5. `add_suggestion` validates category identity, evidence references, schema fields, duplicate
   fingerprints, and store capacity before mutating state.
6. `remove_suggestion` accepts a stable store-assigned suggestion ID, never a mutable display
   number, and is idempotent when the ID is already absent.
7. `more_suggestions` increments a bounded request counter and returns a prompt-like tool result
   containing the remaining capacity and current category gaps.
8. Tool operations mutate a working copy and become visible in the final result only after the
   post-critique generator completes successfully.
9. Provider, schema, timeout, cancellation, and tool failures return typed failures or the last
   committed snapshot according to the existing service failure policy.
10. The service returns the existing frozen `SuggestionResult` built from the committed snapshot,
    and no model-produced prose becomes the public result source of truth.

### Non-Functional Requirements

- Tool names and schemas must pass the SDK's construction-time validation.
- The Codex filesystem remains read-only and approval mode remains deny-all; only the three
  in-memory tools receive the explicitly allowed write permission.
- Store size, suggestion count, and tool-call count are bounded before provider work begins.
- Category order and suggestion order remain deterministic across identical tool traces.
- Tool calls, mutation outcomes, stage calls, elapsed time, and usage remain observable without
  logging caller context bodies or credentials.
- The installed wheel must contain all changed prompt assets and the SDK pin must resolve to the
  custom-tool-capable revision.

---

## 5. High-Level Design

Add a `SuggestionStore` collaborator under `services/suggestions/` that owns validated,
run-local active suggestions and exposes a copy-on-write working view. The existing initial
generator seeds the store from `SuggestionCandidateBatch`. The critic reads a frozen rendering of
that store and returns the current `SuggestionCritiqueArtifact` unchanged as a semantic contract.

The service then creates a new generator agent for each configured curation pass. Its system prompt
consists of the fixed generator instructions followed by a JSON-encoded `<critic_feedback>` block
that is explicitly marked as review data. Its context contains the current store snapshot. Its
tool tuple contains only bound store operations. The agent's final structured reply is a
completion receipt; the store snapshot, not that echoed reply, is authoritative. A later pass
reviews the committed result of the previous pass, but Python never decides which candidate a
critic verdict should edit.

```text
[initial generator]
        -> SuggestionCandidateBatch
        -> [committed SuggestionStore snapshot]
        -> [critic -> SuggestionCritiqueArtifact]
        -> [fresh generator + critic_feedback + working-store tools]
        -> [commit working store]
        -> (repeat critic/curator up to --rounds)
        -> [existing SuggestionResult]
```

The SDK adapter remains the only module importing SDK symbols. It will pass tool instances and the
narrow permission policy through the existing lazy binding. The revision prompt and host-side
candidate decision loop are deleted; the existing `--rounds` setting remains the outer pass cap.
Result grouping and expanded limits are intentionally left to later PRs so this change has one
clear responsibility.

---

## 6. Detailed Design

### 6.1 SuggestionStore

**File(s):** `src/vidbyte_cli/services/suggestions/store.py`  
**Type:** New file

#### What it does

Owns one run's ordered mapping of stable suggestion IDs to validated drafts, category capacity,
duplicate fingerprints, tool counters, and copy-on-write commit behavior. It exposes snapshots as
immutable tuples so callers cannot mutate the service's source of truth behind its validation.

#### Interface / API

```python
class SuggestionStore:
    def seed(self, drafts: tuple[SuggestionDraft, ...]) -> None: ...
    def snapshot(self) -> tuple[SuggestionIdea, ...]: ...
    def working_copy(self) -> "SuggestionStore": ...
    def commit_from(self, working: "SuggestionStore") -> None: ...
    def add(self, category_id: str, draft: SuggestionDraft) -> str: ...
    def remove(self, suggestion_id: str) -> bool: ...
    def request_more(self) -> str: ...
    def tools(self) -> tuple[object, ...]: ...
```

#### Logic / Algorithm

1. Seed drafts in stable order and assign `idea-###` IDs in the host.
2. Validate the category registry, evidence manifest, schema, aggregate limits, and normalized
   duplicate fingerprint before each add.
3. Preserve insertion order and stable IDs across snapshots; a removal never renumbers another
   suggestion.
4. Count tool calls and `more_suggestions` requests before performing the operation.
5. Build `@tool` callables bound to the store and expose only those callables to the generator.
6. Commit the working copy by replacing the active snapshot only after the agent run succeeds.

#### Edge Cases & Error Handling

- Unknown categories, mismatched category fields, invalid evidence, duplicate content, malformed
  drafts, capacity overflow, and tool budgets produce failed tool results with no state change.
- Removing an unknown ID is an idempotent no-op with a clear result message.
- A timeout or cancellation discards the working copy and retains the last committed snapshot.
- Store corruption or an impossible invariant raises a typed service failure rather than returning
  an apparently valid result.

### 6.2 SuggestionService orchestration

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`  
**Type:** Modified

#### What it does

Replaces host-side critique interpretation and revision turns with an initial-generator followed by
bounded critique-and-tool-enabled-generator passes. It remains responsible for request validation,
provider error translation, result construction, and deterministic final selection checks.

#### Interface / API

```python
class SuggestionService:
    def run(self, request: SuggestionRequest) -> SuggestionResult: ...
```

#### Logic / Algorithm

1. Validate the request and load the SDK lazily.
2. Run the initial generator and seed the store from its typed batch.
3. For each configured round, run the critic against the committed snapshot and validate its exact
   candidate coverage.
4. Build a working store and a fresh generator whose system prompt contains canonical critique
   JSON and whose context contains the working snapshot.
5. Run the generator, require its completion receipt, and commit the working store.
6. Stop early when the pass makes no mutations; otherwise continue until the round cap.
7. Convert the committed ideas through existing category/evidence/deduplication/handoff checks
   and construct the existing `SuggestionResult`.

#### Edge Cases & Error Handling

- An empty initial batch returns the existing count-shortfall/no-suggestions result without a
  curator call.
- A malformed critic artifact fails closed as a typed schema/provider failure; it is never treated
  as permission to revise unreviewed data.
- A curator timeout, cancellation, provider error, or malformed completion returns the initial
  committed snapshot as partial when one exists.
- The critic feedback block is length-bounded and canonicalized before prompt construction.

### 6.3 SDK tool binding

**File(s):** `src/vidbyte_cli/services/suggestions/sdk.py`  
**Type:** Modified

#### What it does

Extends the strict local settings dataclass to carry arbitrary SDK-compatible tools and a
permission policy without importing SDK classes outside the lazy adapter.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SuggestionAgentSettingsInput:
    role: Literal["generator", "critic"]
    system_prompt: str
    context: SuggestionContextPrimitive
    output_schema: type | Mapping[str, Any]
    provider: str | None = None
    model: str | None = None
    tools: tuple[Any, ...] = ()
    tool_permission_policy: Any | None = None
```

#### Logic / Algorithm

1. Validate tool declarations as a tuple and retain the existing strict role/context/schema
   checks.
2. Resolve the SDK's `PermissionPolicy` lazily when tools are present.
3. Pass the tools and policy to `CodexHarnessAgentSettings` alongside the existing read-only
   Codex settings.
4. Leave critic agents with no mutation tools.

#### Edge Cases & Error Handling

- A non-callable or malformed tool fails at settings construction before a provider process
  starts.
- An unavailable SDK raises `SuggestionSdkUnavailable` before a model call.
- A tool permission denial is returned by the SDK as a failed tool result; it does not execute the
  callable.

### 6.4 Prompt assets

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/generator.md`,
`src/vidbyte_cli/services/suggestions/prompts/library.py`  
**Type:** Modified

#### What it does

Documents the generator's two responsibilities: producing the initial typed batch and, in a
separate fresh context, using the store tools to apply critique-backed edits. The prompt loader
renders the fixed system prompt and a bounded feedback block without embedding prose in Python.

#### Interface / API

```python
class SuggestionPrompts:
    def generator_system(self, critic_feedback: str = "") -> str: ...
```

#### Logic / Algorithm

1. Keep the authored generator identity, goal, checklist, and output contract in Markdown.
2. Append a fixed instruction describing `<critic_feedback>` as untrusted review data.
3. Append canonical JSON only after schema validation and delimiter escaping.
4. Add explicit instructions for stable IDs, minimal edits, tool use, and finishing when the slate
   is valid.

#### Edge Cases & Error Handling

- Empty feedback produces the unchanged initial generator prompt.
- Feedback larger than the configured bound is rejected before agent creation.
- Prompt assets must remain package data and pass the existing XML-section lint contract.

### 6.5 Remove revision stage

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/revision.md`  
**Type:** Deleted

#### What it does

Removes the prompt whose only purpose was the deleted host-controlled revision pass.

#### Interface / API

N/A - no replacement public API; the post-critique generator uses the generator system prompt
and tools.

#### Logic / Algorithm

1. Delete the revision asset.
2. Remove its loader method and wheel-manifest entry.
3. Ensure no source or test references `revision_system` or `_revise`.

#### Edge Cases & Error Handling

- An installed wheel must not contain a stale revision asset or attempt to load it.
- Existing result and handoff commands remain model-free and unaffected.

### 6.6 SDK dependency pin

**File(s):** `pyproject.toml`  
**Type:** Modified

#### What it does

Moves the CLI's Git dependency from the pre-tool SDK commit to `d8483257` or a later released
revision containing the merged Codex custom-tool implementation.

#### Interface / API

N/A - packaging dependency only.

#### Logic / Algorithm

1. Pin the exact tested SDK revision.
2. Build a wheel and install it in a clean environment through the canonical gate.
3. Confirm help paths still work when the optional SDK import is unavailable.

#### Edge Cases & Error Handling

- A stale editable SDK must not influence local verification; run with the checkout's explicit
  environment and inspect the imported package path if mypy or tests disagree with CI.

---

## 7. Data Model Changes

### 7.1 Run-local SuggestionStore

**Change type:** New

```python
category_id: str -> ordered mapping[suggestion_id: str, SuggestionDraft]
```

**Migration strategy:** N/A - the store exists only during one process invocation and is never
persisted.

### 7.2 Existing suggestion wire models

**Change type:** Unchanged

`SuggestionDraft`, `SuggestionIdea`, `SuggestionCritiqueArtifact`, and `SuggestionResult` remain
the public contracts in this PR. The grouped result model is deliberately deferred.

**Migration strategy:** N/A - no serialized schema change.

---

## 8. API Changes

### 8.1 In-process SDK settings API

**Change type:** Modified

**Request:** `SuggestionAgentSettingsInput` gains `tools` and `tool_permission_policy` fields.

**Response:** The SDK receives the same values in `CodexHarnessAgentSettings`.

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid tool declaration or policy fails before provider launch |
| N/A | Denied tool call returns a failed SDK tool result |
| N/A | Provider or schema failure follows existing typed CLI failure handling |

### 8.2 Generator tool API

**Change type:** New in-process model-facing tools

**Request:**

```json
{
  "category_id": "verification",
  "suggestion": "SuggestionDraft-shaped object"
}
```

**Response:** A bounded text result containing the assigned ID or a validation failure.

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Unknown category, invalid draft, duplicate, invalid evidence, or capacity overflow |
| N/A | Unknown removal ID is an idempotent no-op |
| N/A | Tool budget exhaustion prevents mutation |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `src/vidbyte_cli/services/suggestions/store.py` | Run-local validated store and bound tools |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Replace revision loop with tool-enabled generator |
| MODIFY | `src/vidbyte_cli/services/suggestions/sdk.py` | Pass arbitrary tools and permission policy |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add the curator completion receipt |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/generator.md` | Document tool-driven curation |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/library.py` | Render feedback-aware system prompt |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/curation.md` | Curator turn instructions |
| DELETE | `src/vidbyte_cli/services/suggestions/prompts/revision.md` | Remove host-controlled revision stage |
| MODIFY | `scripts/run_ci.py` | Remove deleted revision asset from wheel manifest |
| MODIFY | `scripts/test_suggestions.py` | Update fake SDK and verify tool-driven flow |
| CREATE | `scripts/test-suggestion-generator-tools.py` | Executable feature verification script |
| MODIFY | `pyproject.toml` | Pin SDK revision with custom-tool support |

---

## 10. Testing Plan

### Unit Tests

- `SuggestionStore` accepts a valid draft and assigns a stable ID. **[Edge Case]**
- `SuggestionStore` rejects an unknown category, mismatched primary category, invalid evidence,
  duplicate fingerprint, and capacity overflow without changing state. **[Hidden Failure]**
- Removing one ID leaves all other IDs and their order unchanged. **[Silent Failure]**
- Removing an already absent ID is idempotent. **[Hidden Assumption]**
- `more_suggestions` increments its counter and reports remaining capacity. **[Edge Case]**
- Tool counters reject the first call beyond the configured cap. **[Hidden Failure]**
- A failed add does not partially insert a draft. **[Silent Failure]**
- A working copy can be discarded without changing the committed snapshot. **[Hidden Assumption]**
- Critique JSON is canonical, bounded, and delimited before prompt injection. **[Edge Case]**
- The SDK settings adapter forwards tools and policy while critic settings remain tool-free.
  **[Hidden Assumption]**

### Integration Tests

- Fake initial generator, critic, and curator produce an added replacement and removed original;
  the final result reflects the committed store. **[Edge Case]**
- Curator timeout returns the initial committed snapshot and a partial stop reason. **[Hidden Failure]**
- Curator schema failure does not expose half-applied working-store mutations. **[Silent Failure]**
- Critic output with a missing or unknown candidate ID fails before the curator starts.
  **[Hidden Assumption]**
- A generator that calls `remove_suggestion` by a display number receives a validation failure and
  cannot delete an unrelated ID. **[Hidden Failure]**
- The clean installed wheel loads the new prompt assets and the pinned SDK adapter. **[Edge Case]**

### Manual / QA Test Cases

1. Given three generated suggestions and a critic asking for one repair, run the command and verify
   the output contains the repaired active suggestion, not a host-generated revision artifact.
   **[Edge Case]**
2. Given a curator that requests more ideas repeatedly, verify the cap is reported and the process
   terminates with a truthful partial or complete stop reason. **[Hidden Failure]**
3. Given identical fake tool traces, verify JSON output has identical IDs and ordering.
   **[Silent Failure]**
4. Given caller context containing instruction-like text, verify it appears only as bounded review
   data and cannot grant execution authority or filesystem writes. **[Hidden Assumption]**

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte SDK | Git revision `d8483257` or later | Dynamic Codex tools and permission policy | Experimental Codex dynamic-tool field; pin and wheel-test it |
| Provider configured by caller | Existing provider/model settings | Initial generation, critique, and curation | Timeout, schema violation, cost; handled by typed failures and limits |

---

## 12. Rollout & Deployment

- No feature flag is required because the suggestion agent is already a specialized command and
  this changes only its internal workflow.
- Merge this PR independently before the structured-result and expanded-guardrail PRs.
- Roll back by reverting this branch; the prior revision prompt and loop are restored together.
- The SDK pin must be deployed with the CLI code. A CLI build using the old pin must fail the
  packaging verification rather than silently running without tools.

---

## 13. Open Questions

- [x] Should the public option formerly named `--rounds` be removed in this PR or retained as a
  deprecated no-op until the guardrail PR replaces it with explicit tool budgets? It remains the
  outer critique-and-curation pass cap, so existing callers retain meaningful behavior.
- [ ] Should `remove_suggestion` unknown IDs be a successful no-op or a failed tool result? The
  design chooses idempotent success to make retries safe.
- [ ] Should the curator completion receipt carry a reason enum, or only counts? The design uses a
  minimal typed receipt because the store is authoritative.

---

## 14. Alternatives Considered

### Alternative 1: Keep `_review` and `_revise` and add tools around it

- What: Let Python continue deciding which candidates need revision while also giving the model
  mutation tools.
- Why rejected: It leaves two competing authorities and violates the requested removal of the
  revision algorithm.

### Alternative 2: Inject raw critic text into the system prompt

- What: Concatenate the provider's textual response after the generator instructions.
- Why rejected: It bypasses the existing schema contract and allows caller-derived instruction text
  to become system-level instructions.

### Alternative 3: Let the model return the final suggestion dictionary

- What: Require the curator's structured response to contain the complete final slate.
- Why rejected: The response and tool state can diverge. The typed store is the single source of
  truth; the model only operates it.

### Alternative 4: Use a process-global dictionary

- What: Keep suggestions in a module-level registry shared across calls.
- Why rejected: Concurrent invocations would leak state across users and make retries non-isolated.
