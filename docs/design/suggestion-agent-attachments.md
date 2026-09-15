# Design Doc: Suggestion Agent Shared Attachments

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

Wire the shared `--attach PATH` infrastructure from PR #53 into `agents suggest run`.
The command will resolve explicit files once into an immutable `AttachmentBundle`, carry that
bundle through the validated suggestion request, and give the same bundle to every generator,
critic, revision, and extra-compute call. Text files will use the central snapshot-based
`FileContextItem` adapter and supported images will use native Codex image inputs. The work is
split into three stacked, reviewable PRs so request plumbing, provider execution, and output
accounting can be reviewed independently.

---

## 2. Goals & Non-Goals

### Goals

- Add the repeatable shared `--attach PATH` option to `agents suggest run`.
- Resolve attachments before SDK loading, credentials, model calls, or token use.
- Carry one immutable `AttachmentBundle` across the suggestion request and workflow.
- Reuse `CodexAttachmentInputBuilder` for every suggestion agent invocation.
- Preserve attachment order, text snapshots, hashes, native image inputs, and central limits.
- Include a body-free attachment manifest in suggestion results and dry-run output.
- Keep existing suggestion-specific `--files` semantics unchanged.
- Provide focused verification in each PR and a final executable attachment verification script.

### Non-Goals

- Do not modify PR #53's resolver, limits, typed failures, or Codex adapter behavior.
- Do not make `--files` an alias for `--attach` or remove the existing option.
- Do not make attachments automatically eligible as `ctx-NNN` suggestion evidence references.
- Do not add PDF, DOCX, archive, directory, glob, or arbitrary binary parsing.
- Do not grant the suggestion agents write access or filesystem authority.
- Do not change suggestion ranking, critique, handoff, category, or provider policy.
- Do not add a backend route, database table, migration, or persisted attachment store.

---

## 3. Background & Context

PR #53 merged to `main` as `75d09d2` and deliberately stopped before changing existing agent
commands. It introduced `AgentAttachmentOptions`, `AttachmentResolver`, immutable attachment
models, typed attachment failures, and `CodexAttachmentInputBuilder`. The resolver snapshots
text bytes once and maps images to native local-image inputs, so a future command must pass the
bundle forward rather than reread paths.

The refined suggestion agent on `main` has a strict `SuggestionRequest` boundary, a
`SuggestionContextPrimitive` for semantic suggestion context, a lazy `SuggestionSdk`, and one
`SuggestionService._call_agent()` path shared by generator, critic, revision, and extra-compute
turns. Its current SDK input remains text-only. `--files` is intentionally a separate semantic
input: it parses text/Markdown/JSON into `ctx-NNN` evidence context. Combining it with generic
attachments would duplicate reads and discard native images.

The current checkout branch is stale relative to `main`, so all implementation work will start
from a clean worktree at current `main`. The existing checkout's untracked design documents are
unrelated and will remain untouched. The field guide requires strict request boundaries,
fresh managed context for independent agents, typed failures, sparse comments, and the canonical
`scripts/run_ci.py` gate; this design follows those constraints.

---

## 4. Requirements

### Functional Requirements

1. `agents suggest run --help` exposes repeatable `--attach PATH` using
   `AgentAttachmentOptions`.
2. Click occurrence order is preserved from the command to the resolved bundle.
3. Suggestion request validation rejects malformed attachment values through the shared typed
   failure path before provider work.
4. A valid invocation resolves all attachment paths exactly once and stores the resulting
   immutable `AttachmentBundle` on `SuggestionRequest`.
5. An empty attachment collection remains valid and preserves the current text-only behavior.
6. The service forwards the same bundle to every `_call_agent()` invocation, including generator,
   critic, revision, and extra-compute branches.
7. `SuggestionSdk` uses `CodexAttachmentInputBuilder` so text attachments become
   `FileContextItem` snapshots and images become `CodexLocalImageInput` values.
8. Provider settings remain read-only with denied approvals and are unaffected by attachments.
9. Missing, duplicate, empty, unsupported, oversized, or unreadable attachments fail before
   SDK loading and model execution using PR #53's existing typed failures.
10. `--dry-run` resolves and reports attachment metadata without loading the SDK or making a
    model call.
11. Suggestion results contain a body-free attachment manifest with order, names, kinds, sizes,
    supplied/resolved paths, and SHA-256 hashes.
12. Attachment metadata is not mixed into the suggestion evidence-reference manifest, and
    existing `--files` behavior remains unchanged.
13. The final verification script exercises the complete request-to-agent path with a fake SDK
    boundary and exits non-zero for any failed labeled case.

### Non-Functional Requirements

- Resolution remains synchronous, bounded, and linear in supplied files and bytes read.
- No attachment I/O, SDK import, credential access, or model call occurs during command
  registration or `--help` rendering.
- The source file is read once for text snapshots; later execution cannot observe a changed body.
- Attachment bodies never enter the machine-facing attachment manifest or diagnostics.
- Lazy SDK imports remain intact so category/help and dry-run paths work without Codex symbols.
- The new Python code follows the repository's one-line signatures, sparse invariant comments,
  strict typing, and line-length settings.
- Existing public suggestion result fields and `--files` contracts remain backward compatible.

---

## 5. High-Level Design

The first PR adds the option and request plumbing. The command applies the shared decorator, the
request builder validates the ordinary suggestion arguments, resolves the parsed attachment
paths through `AgentAttachmentOptions`, and stores the resulting `AttachmentBundle` on the
frozen `SuggestionRequest`. This keeps filesystem validation before any provider side effect.

The second PR extends the local SDK input value with the bundle and makes `SuggestionSdk` call
`CodexAttachmentInputBuilder`. The service's existing `_call_agent()` method supplies the request
bundle for every independent model call. The SDK adapter remains lazy and continues to construct
fresh read-only, deny-all agent settings with a fresh context manager per agent.

The third PR adds the body-free result manifest, dry-run/output assertions, and the complete
verification script plus CI registration. Attachment metadata remains a separate field because
`context_manifest` describes suggestion-domain `ctx-NNN` evidence, while the shared attachment
manifest describes provider-neutral file snapshots.

```text
--attach PATH (Click)
        |
        v
AgentAttachmentOptions.resolve
        |
        v
AttachmentResolver  -- one bounded read --> AttachmentBundle
        |
        v
SuggestionRequest.attachments
        |
        v
SuggestionService._call_agent (all branches)
        |
        v
SuggestionSdk.run_input
        |
        v
CodexAttachmentInputBuilder
   |                    |
   v                    v
text FileContextItem   native local image
```

---

## 6. Detailed Design

### 6.1 Suggestion command option

**File(s):** `src/vidbyte_cli/commands/agents/suggestion/suggest.py`
**Type:** Modified (PR 1)

#### What it does

Adds the shared repeatable `--attach PATH` option to `agents suggest run` without moving it to
the root command or duplicating help and validation prose.

#### Interface / API

```python
_ATTACHMENT_OPTIONS = AgentAttachmentOptions()


def register(self, parent: click.Group) -> None: ...
```

The decorator is applied to the existing `run` callback. Click stores repeated values under the
`attachments` key as a tuple of `Path` objects.

#### Logic / Algorithm

1. Instantiate the stateless shared option helper near the existing command help constants.
2. Apply its decorator to the `run` callback.
3. Leave all existing suggestion options and decorator order intact.
4. Keep the helper import free of SDK imports so command help remains offline.

#### Edge Cases & Error Handling

- Zero occurrences produce an empty bundle.
- Multiple occurrences preserve Click order.
- A programmatic non-tuple or non-`Path` value is rejected by the shared helper.
- Filesystem failures are raised by existing attachment failure classes, not new command-local
  errors.

### 6.2 Request attachment plumbing

**File(s):** `src/vidbyte_cli/commands/agents/suggestion/request_builder.py`
**Type:** Modified (PR 1)

#### What it does

Extends the strict command-input dataclass and builder so raw paths become one immutable bundle
before constructing the service request.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SuggestionRunInput:
    attachments: tuple[Path, ...] = ()


class SuggestionRequestBuilder:
    def build(self, raw: dict[str, object]) -> SuggestionRequest: ...
```

#### Logic / Algorithm

1. Include `attachments` in `SuggestionRunInput` and validate its tuple-of-`Path` shape.
2. Validate goal, semantic context, categories, counts, and execution settings first.
3. Call `AgentAttachmentOptions.resolve` with the validated attachment tuple.
4. Continue using `SuggestionContextBuilder` only for existing `--files` semantic context.
5. Construct `SuggestionRequest` with the existing context primitive plus the resolved bundle.
6. Translate only malformed suggestion input into `SuggestionInputInvalid`; preserve existing
   attachment `CliError` subclasses so their actionable codes and descriptions survive.

#### Edge Cases & Error Handling

- Invalid suggestion settings do not cause attachment reads.
- No paths create `AttachmentBundle()`.
- A changed source after resolution cannot alter the text content in the bundle.
- Existing `--files` errors retain their existing `SuggestionContextUnreadable` behavior.

### 6.3 Suggestion request contract

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified (PR 1)

#### What it does

Makes the resolved attachment bundle an explicit part of the frozen service request while
preserving default construction for callers that provide no attachments.

#### Interface / API

```python
class SuggestionRequest(BaseModel):
    attachments: AttachmentBundle = Field(default_factory=AttachmentBundle)
```

The type imports `AttachmentBundle` from `vidbyte_cli.types.attachments`. No filesystem access
or provider code is added to the type module.

#### Logic / Algorithm

1. Add the bundle field with an empty-bundle default.
2. Keep `extra="forbid"` and `frozen=True` on the request.
3. Leave `context_items` compatibility behavior and context-goal validation unchanged.
4. Expose no mutable path list; callers receive the immutable bundle contract.

#### Edge Cases & Error Handling

- A request created by an existing caller without `attachments` validates as before.
- A non-bundle attachment value is rejected by Pydantic before service execution.
- Bundle total and path uniqueness invariants remain owned by `AttachmentBundle`.

### 6.4 SDK run-input adapter

**File(s):** `src/vidbyte_cli/services/suggestions/sdk.py`
**Type:** Modified (PR 2)

#### What it does

Extends the local SDK boundary to carry an attachment bundle and delegates provider-specific
conversion to PR #53's lazy `CodexAttachmentInputBuilder`.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SuggestionTextInput:
    prompt: str
    attachments: AttachmentBundle = field(default_factory=AttachmentBundle)


def run_input(self, request: SuggestionTextInput) -> Any: ...
```

#### Logic / Algorithm

1. Keep `SuggestionTextInput` as a strict local dataclass.
2. Accept the immutable bundle as an optional empty default.
3. Construct `CodexAttachmentInputBuilder` only when a run input is requested.
4. Call `build(request.prompt, request.attachments)`.
5. Preserve lazy SDK symbol loading and existing provider/schema error classification.

#### Edge Cases & Error Handling

- Empty bundles produce the same semantic text-only input shape as before.
- Text uses the resolver snapshot and hash metadata, not a second filesystem read.
- Images remain native local-image inputs.
- A missing SDK symbol still raises `SuggestionSdkUnavailable` at the existing lazy boundary.

### 6.5 Workflow forwarding

**File(s):** `src/vidbyte_cli/services/suggestions/service.py`
**Type:** Modified (PR 2)

#### What it does

Passes the same request bundle through the common agent-call path so every suggestion stage has
the same explicit attachment audience.

#### Interface / API

```python
async def _call_agent(..., request: SuggestionRequest, ...): ...
```

The existing method signature remains stable; only construction of `SuggestionTextInput` gains
`attachments=request.attachments`.

#### Logic / Algorithm

1. Keep local limit checks before agent construction.
2. Build `SuggestionTextInput(prompt=prompt, attachments=request.attachments)`.
3. Use that input in both timeout branches.
4. Leave generator, critic, revision, and extra-compute scheduling unchanged.
5. Continue creating fresh read-only agents and independent context managers for each call.

#### Edge Cases & Error Handling

- A critic or revision cannot silently lose the bundle because all calls share this method.
- Timeout and provider failures retain existing workflow handling.
- Attachment data does not grant write tools, change sandbox policy, or alter approval mode.

### 6.6 Result attachment manifest

**File(s):** `src/vidbyte_cli/types/suggestions.py`, `src/vidbyte_cli/services/suggestions/service.py`,
`src/vidbyte_cli/commands/agents/suggestion/render.py`
**Type:** Modified (PR 3)

#### What it does

Reports safe attachment metadata alongside suggestion results and dry-run results without
embedding file bodies or treating attachments as suggestion evidence references.

#### Interface / API

```python
class SuggestionResult(BaseModel):
    attachment_manifest: tuple[dict[str, object], ...] = ()
```

The service fills this from `request.attachments.manifest()`. Human rendering names the count
and metadata according to the existing renderer policy; JSON and JSONL serialization carry the
same body-free field.

#### Logic / Algorithm

1. Add a default-empty result field after the existing context manifest.
2. Fill it for normal and dry-run results from the immutable request bundle.
3. Preserve manifest ordering and all fields emitted by the shared bundle method.
4. Do not copy `content` into the result or merge entries into `context_manifest`.
5. Keep human output concise while machine output remains lossless metadata.

#### Edge Cases & Error Handling

- Empty attachments serialize as an empty tuple/list according to the existing output format.
- A text body never appears in the attachment manifest.
- Full SHA-256 values remain intact rather than truncating them for display data.
- Existing result consumers that ignore unknown additive fields remain compatible.

### 6.7 Verification coverage

**File(s):** `scripts/test-suggestion-agent-attachments.py`, `scripts/run_ci.py`,
`docs/design/suggestion-agent-attachments.md`
**Type:** Created/Modified (PR 3; focused tests may be added in PRs 1 and 2)

#### What it does

Exercises the complete integration at the local SDK boundary with temporary text/image files and
a fake SDK adapter. It prints one labeled `PASS` or `FAIL` per case and a final count, then exits
non-zero if any case fails. `run_ci.py` registers it as a source gate after the existing suggestion
suite.

#### Interface / API

```python
def main() -> int: ...
```

#### Logic / Algorithm

1. Add temporary UTF-8 text and supported image fixtures.
2. Build requests through `SuggestionRequestBuilder` using repeated attachment paths.
3. Inspect bundle order, snapshots, hashes, and body-free manifests.
4. Run `SuggestionService` with a fake SDK that records every `SuggestionTextInput`.
5. Assert all stage calls received the same bundle and that empty requests remain text-only.
6. Force invalid files and a fake SDK import boundary to verify preflight and lazy behavior.
7. Print the required summary and return failure status when any assertion fails.

#### Edge Cases & Error Handling

- The script must not call a live provider or require credentials.
- It must use `PYTHONPATH=src` or its own path insertion so an editable install cannot mask the
  worktree under test.
- Temporary files are cleaned by context managers even when an assertion fails.

---

## 7. Data Model Changes

### 7.1 `SuggestionRequest`

**Change type:** Modified

```python
attachments: AttachmentBundle = Field(default_factory=AttachmentBundle)
```

This is an in-process model change only. No persisted suggestion request exists, so no migration
is required. Existing callers receive the empty bundle by default.

### 7.2 `SuggestionResult`

**Change type:** Modified

```python
attachment_manifest: tuple[dict[str, object], ...] = ()
```

This is an additive versioned output field. The existing schema version and result kind remain
unchanged because the field is optional for readers and contains no changed interpretation of
existing fields.

**Migration strategy:**

- Forward migration: none; new producers add the field and old consumers may ignore it.
- Rollback plan: revert the result-field commit; no stored documents need cleanup.

---

## 8. API Changes

N/A - this feature changes only the local CLI command and in-process/provider input contracts. It
does not add or modify a Vidbyte backend endpoint.

---

## 9. File Change Manifest

The implementation is intentionally split into three stacked PRs. PR 2 targets PR 1's branch and
PR 3 targets PR 2's branch; each can be retargeted to `main` after its predecessor merges.

### PR 1 - request and CLI plumbing (`feat/suggestion-agent-attachments-request`)

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/suggest.py` | Declare shared `--attach` option. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/request_builder.py` | Validate paths and resolve one bundle. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Carry `AttachmentBundle` on `SuggestionRequest`. |
| MODIFY | `scripts/test_suggestions.py` | Add request-level attachment parsing and ordering checks. |

### PR 2 - provider execution wiring (`feat/suggestion-agent-attachments-execution`)

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `src/vidbyte_cli/services/suggestions/sdk.py` | Convert bundle through the shared Codex adapter. |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Forward the bundle to every agent call. |
| MODIFY | `scripts/test_suggestions.py` | Verify generator/critic/revision propagation and native inputs. |

### PR 3 - output manifest and final gate (`feat/suggestion-agent-attachments-output`)

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add body-free attachment manifest to results. |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Populate manifest for normal and dry-run results. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/render.py` | Render manifest under existing output policy. |
| CREATE | `scripts/test-suggestion-agent-attachments.py` | Full labeled request/provider/output verification. |
| MODIFY | `scripts/run_ci.py` | Register final attachment verification source gate. |
| MODIFY | `docs/design/suggestion-agent-attachments.md` | Record implementation status and deviations. |

No files are deleted. PR #53 files are reused unchanged.

---

## 10. Testing Plan

### Unit Tests

#### Request and resolver boundary (PR 1)

- `AgentAttachmentOptions` renders a repeatable option and preserves two occurrence paths in
  order. **[Silent Failure]**
- An omitted option builds an empty bundle and does not alter the existing request defaults.
  **[Edge Case]**
- A non-tuple or tuple containing a non-`Path` fails through the shared invalid-input contract.
  **[Hidden Assumption]**
- Invalid goal/count/category is rejected before a supplied attachment path is read.
  **[Hidden Failure]**
- A text attachment is snapshotted once; mutating the file after request construction leaves the
  bundle content and hash unchanged. **[Silent Failure]**
- A duplicate path supplied through two spellings is rejected by the shared resolver.
  **[Edge Case]**

#### Provider execution boundary (PR 2)

- An empty bundle still produces the semantic text-only input. **[Edge Case]**
- One text and one image map to one text input, one `FileContextItem`, and one native image input
  in supplied order. **[Silent Failure]**
- `SuggestionSdk.run_input` rejects an untyped local request instead of silently coercing it.
  **[Hidden Assumption]**
- Generator, critic, revision, and extra-compute calls all receive the same bundle instance and
  attachment hashes. **[Hidden Failure]**
- Read-only sandbox and deny-all approval settings remain unchanged when attachments exist.
  **[Hidden Assumption]**
- Missing SDK symbols remain lazy for help/category paths and fail only at model-backed execution.
  **[Hidden Failure]**

#### Result and verification boundary (PR 3)

- Normal and dry-run results include an ordered body-free manifest. **[Silent Failure]**
- The manifest contains the full hash and size but never `content`. **[Hidden Failure]**
- Empty attachments serialize as an empty manifest without changing existing result fields.
  **[Edge Case]**
- Existing semantic `context_manifest` refs do not acquire attachment entries accidentally.
  **[Hidden Assumption]**
- Human, JSON, and JSONL renderers do not print attachment bodies to stdout. **[Silent Failure]**

### Integration Tests

- Invoke `agents suggest run --help` through the public command tree and assert `--attach` is
  present without importing Codex.
- Build a request with repeated text/image paths and run the service against a fake SDK that
  records every typed input. Assert every stage sees the same attachment bundle.
- Run `--dry-run` with an invalid and a valid attachment; assert invalid input fails before SDK
  loading and valid output contains metadata only.
- Run the existing suggestion suite with no attachments to prove regression-free text-only behavior.
- Build and inspect the wheel to ensure the new verification script and existing suggestion prompt
  assets are present; run the complete `scripts/run_ci.py` gate.

### Manual / QA Test Cases

1. Given two explicit files, when the caller repeats `--attach`, then the result manifest preserves
   command order and each hash matches the captured bytes. **[Silent Failure]**
2. Given a missing, empty, duplicate, unsupported, or oversized file, when `run` is invoked, then
   a typed attachment failure appears before credentials or provider startup. **[Hidden Failure]**
3. Given a text file changed after request construction, when generation occurs, then the agent
   receives the original snapshot rather than the changed body. **[Silent Failure]**
4. Given a PNG and a Markdown file, when generator and critic calls run, then both calls receive
   native image/text context and retain read-only deny-all settings. **[Hidden Assumption]**
5. Given `--dry-run`, when the command is invoked without the optional SDK installed, then it
   returns the attachment manifest and never attempts provider work. **[Edge Case]**
6. Given the existing `--files` option, when it is used without `--attach`, then its `ctx-NNN`
   references, truncation, and evidence validation remain unchanged. **[Hidden Assumption]**
7. Given JSON output, when an attachment is supplied, then stdout contains metadata but no file
   body, while diagnostics remain on stderr. **[Silent Failure]**

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Click | `>=8.1,<9` | Parse repeatable `--attach` values. | Low; already required. |
| Pydantic | `>=2.6,<3` | Validate request and result contracts. | Low; already required. |
| Vidbyte SDK Codex facade | Existing pinned git revision | Convert bundles and run agents. | Medium; adapter remains lazy and fake-tested. |
| Python filesystem APIs | Python 3.11+ | Existing resolver snapshot behavior. | Low; delegated to PR #53. |

No backend, network, database, payment, or credential service is introduced.

---

## 12. Rollout & Deployment

- No feature flag is needed; the new option is additive and opt-in.
- Merge PR 1, then PR 2, then PR 3. Until PR 2 lands, the option validates and is carried but
  does not reach provider input; the PR body will state that staged behavior explicitly.
- After each PR merges, retarget the next stacked PR to `main` and rerun the full gate.
- Rollback is a normal revert in reverse order: output/gate, execution, then request plumbing.
  No persisted data or migration rollback is required.

---

## 13. Open Questions

- [ ] Should a later feature assign stable suggestion evidence references to generic attachments,
  or should they remain supplemental provider context only?
- [ ] Should `--files` eventually be deprecated in favor of `--attach`, or should both remain
  because their semantic and provider contracts differ?
- [ ] Should result manifests expose absolute resolved paths in all output modes, or should a
  future privacy policy redact them while retaining hashes?
- [ ] Should the shared adapter eventually support additional provider-native binary types?

---

## 14. Alternatives Considered

### Alternative 1: Read attachment files in `SuggestionContextBuilder`

- **What:** Route `--attach` through the existing suggestion-specific file reader.
- **Why rejected:** It would reread snapshots, discard native image inputs, duplicate limits and
  errors, and make the shared PR #53 contract decorative rather than authoritative.

### Alternative 2: Pass paths inside the prompt

- **What:** Append attachment paths to the generated prompt and let the agent inspect them.
- **Why rejected:** Paths are not content snapshots, images are not native inputs, the file may
  change after validation, and this would expand implicit filesystem access.

### Alternative 3: Add a root-level global `--attach`

- **What:** Make every CLI command accept attachments.
- **Why rejected:** Administrative and API commands have no agent input; the option would be
  misleading and would complicate command help and root parsing.

### Alternative 4: Attach only during initial generation

- **What:** Add files to the first generator call but not critic or revision calls.
- **Why rejected:** The critic and revision agents would evaluate ideas without the evidence the
  generator saw, producing inconsistent multi-agent behavior.

### Alternative 5: Merge attachments into `context_manifest`

- **What:** Turn generic attachment metadata into suggestion `ctx-NNN` evidence entries.
- **Why rejected:** It conflates provider file identity with suggestion semantic context and would
  require a deliberate stable-ref/evidence contract not provided by PR #53. That is a follow-up,
  not a file-orchestration change.

### Alternative 6: Implement the whole feature in one PR

- **What:** Combine CLI plumbing, SDK execution, output schema, and verification in one branch.
- **Why rejected:** The user requested individual PRs, and the three boundaries have different
  review risks. Stacking keeps each change narrow while preserving one eventual end-to-end path.
