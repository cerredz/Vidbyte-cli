# Design: Native-tool task-board decomposition

## 1. Overview

Replace the stale PR #43 task-board decomposition protocol with a native Codex tool
integration in `vidbyte-cli`. A parent task may call `decompose_tool` with an ordered list of
self-contained subtasks; the CLI records the validated call, replaces that parent in the live
linear board, and runs each child in a fresh isolated Codex agent.

The implementation consumes the already-merged SDK native-tool support from
`vidbyte-sdk` commit `d8483257717d6e1f99e594462b8926e9b5de525a` (PR #434). The CLI dependency
pin moves to that revision. The SDK itself is not changed by this PR.

The old PR's fenced `decompose` JSON block is deliberately removed from the contract. Tool
arguments are schema-validated by the SDK, while task-board policy and the in-place splice stay
owned by the CLI runtime primitive.

## 2. Goals & Non-Goals

### Goals

- Add an opt-in `--allow-decompose` task-board mode.
- Register one safe native `decompose_tool` only on eligible depth-zero parent turns.
- Preserve ordered, in-place expansion with a maximum of ten accepted subtasks per parent and
  a maximum of 500 live board tasks.
- Normalize blank, overlong, and case-insensitive duplicate candidates deterministically.
- Keep child prompts isolated and prevent children from decomposing again.
- Preserve existing retry, completion, failure, result, and admission behavior.
- Reject checkpointing and DAG mode before credentials, payment, or host execution because
  expansion shifts board indices.
- Verify the tool schema and native settings wiring offline without starting Codex or calling
  a Vidbyte endpoint.

### Non-Goals

- No changes to `vidbyte-sdk` source; native tool support is consumed as a dependency.
- No decomposition for checkpointed, resumed, replayed, repaired, or DAG boards.
- No recursive decomposition, parallel child execution, dependency inference, or child context
  handoff.
- No model-generated parsing of final text and no compatibility mode for the fenced block.
- No new admission capability or price; one task-board admission still covers the run.

## 3. Background & Context

PR #43 was based on a text convention: the model appended a fenced JSON array to its final
reply, and the CLI parsed that reply after completion. That makes a model-facing protocol share
the same channel as the user-visible answer and leaves malformed or partial text at the boundary.

The SDK now exposes `CodexHarnessAgentSettings.tools`, translates `vidbyte.tools` tools into
Codex dynamic tools, and executes native calls through its `ToolExecutor`. The CLI can therefore
declare a real function-shaped contract and receive the accepted subtasks during the same agent
turn. `CodexClientSettings.experimental_api=True` is required whenever tools are present.

Current task-board `main` already owns checkpoints, DAG execution, budgets, retries, bounded
handoffs, and the result model. Those features are index-sensitive and are intentionally kept
outside the self-mutating decomposition loop.

## 4. Requirements

### Functional

1. The command exposes `--allow-decompose/--no-allow-decompose`, defaulting to off.
2. The command exposes `--max-subtasks`, constrained to 2 through 10, defaulting to 5.
3. Enabling decomposition with checkpointing or `--type dag` raises the existing typed CLI
   usage failure before credentials, admission, or host execution.
4. An eligible parent agent receives one native tool named `decompose_tool` with a required
   array-of-strings `subtasks` parameter.
5. The tool accepts candidates in declaration order, strips surrounding whitespace, drops blank
   or over-20,000-character strings, removes case-insensitive duplicates, and caps the result at
   `max_subtasks`.
6. Fewer than two valid candidates means the parent remains a normal completed task. Invalid
   SDK argument shapes likewise produce a safe tool failure and never mutate the board.
7. A successful call replaces the parent at its current index. Later original tasks shift right;
   the parent step remains represented in execution-order output as the decomposition event.
8. The live board never exceeds 500 tasks. An expansion that cannot fit at least two children is
   not applied; an expansion that can fit fewer than the requested maximum is truncated to fit.
9. Each child runs once in a fresh agent with only its own task. Children do not receive prior
   summaries and do not receive `decompose_tool`.
10. The parent is allowed one accepted decomposition per attempt. A retry creates a fresh tool
    capture; an accepted call from a failed attempt is discarded.
11. Plain final text is stored as the normal result. No `decompose` fence is extracted or
    removed.
12. Existing stop-on-error and continue-on-error semantics apply to parents and children. A
    failed parent never splices children.
13. Existing task-board result accounting reports completed, failed, tokens, stopped reason, and
    execution-order steps consistently with the mutable linear run.

### Non-functional

- Tool registration must remain lazy so command help and offline validation do not require a
  live Codex process.
- The CLI must only use the SDK public tool/settings surface; it must not import the SDK's
  private Codex bridge.
- Native tool descriptions and parameter names must be stable, meaningful, and schema-visible.
- Candidate normalization and splice decisions must be deterministic and free of network calls.
- New verification must be an executable, offline script with a nonzero exit status on failure.
- Existing canonical CLI checks must remain green, including packaging of the runtime prompt.

## 5. High-Level Design

The command layer validates options and constructs frozen `TaskBoardSettings`. The session
selects the existing checkpoint/DAG runner or, when enabled, a separate mutable linear runner.
For each eligible parent attempt, the session constructs a capture object and a decorated SDK
function tool. The capture records only a normalized tuple; after the turn completes, the session
decides whether the tuple can be spliced into the live board.

```text
CLI options
    -> TaskBoardSettings validation
    -> reject checkpoint/DAG conflicts
    -> TaskBoardCodexSession
         -> normal runner (existing checkpoint/DAG/linear path)
         -> native decomposition runner
              -> eligible parent: tool + isolated prompt + fresh agent
              -> accepted tuple: replace parent in live work list
              -> depth-one child: isolated prompt + fresh agent, no tool
```

The SDK owns dynamic-tool transport, argument validation, permissions, and tool result delivery.
The CLI owns candidate policy, board mutation, depth, retries, and user-facing summaries.

## 6. Detailed Design

### Command and settings

Add the two flags to the existing `run` command and carry them through `TaskBoardOptions` into
`TaskBoardSettings`. Add bounded fields with descriptive model metadata. The command checks the
two index-sensitive conflicts alongside dependency validation. The existing typed
`TaskBoardDecomposeInvalid` failure names the conflicting option and explains the safe rerun.

When decomposition is enabled, the mutable runner is always isolated regardless of the
caller-provided window, handoff, or summary settings. The command emits the existing diagnostic
progress channel's decomposition-isolated notice once.

### Native tool

`TaskBoardDecomposeCapture` is a small per-attempt state holder. Its factory lazily imports the
SDK `tool` decorator and exposes:

```python
decompose_tool(subtasks: list[str]) -> str
```

The tool has the stable name `decompose_tool`, safe permission, and a description explaining
that it replaces the current task, accepts two through the configured maximum self-contained
subtasks, is callable once for an accepted split, and must not be used for child work. The
callable returns a short status string to Codex while the capture retains the tuple needed by
the board. It never mutates the board directly.

The capture uses a lock because the SDK's function adapter may execute synchronous tools in a
worker thread. An invalid normalized list leaves the capture empty and returns corrective tool
feedback; a later valid call in the same turn may then be accepted. Once a valid call is
accepted, later calls return a safe already-accepted message and cannot overwrite the tuple.

### Agent construction

Extend the existing `_build_agent` seam with an optional tool object. Parent attempts pass
`tools=(decompose_tool,)` and explicitly set `experimental_api=True`; ordinary and child
attempts pass no tools and preserve the existing client configuration. The CLI does not access
`CodexToolBridge`, Codex request methods, or provider wire payloads.

### Mutable execution

`TaskBoardCodexSession._run` dispatches to `_run_decomposing` before the existing order/checkpoint
setup. The mutable runner keeps `work: list[str]` and a parallel depth list. At each index:

1. Run the current task with an isolated prompt and a fresh attempt-local capture when it is a
   depth-zero task with room for at least two children.
2. On failure, record one failed step and apply the configured stop policy; discard any capture.
3. On success, add usage and inspect the capture only if the task was eligible.
4. If at least two children fit, replace `work[index:index+1]`, mark all inserted depths one,
   append a completed decomposition event, and process the same index again.
5. Otherwise append the normal completed step and advance the index.

The splice is the only board mutation. It uses the current live length to cap the accepted tuple
at 500 total entries. Because indices can repeat across a parent event and its first child, the
decomposition result keeps the steps in append/execution order rather than applying the normal
index-based sort used by linear and DAG checkpointed runs.

### Prompt and result behavior

The task-board system prompt keeps its generic one-task contract. An eligible user prompt adds a
short native-tool instruction naming `decompose_tool` and its current maximum; no fenced syntax
is mentioned. Child prompts contain only the child task and the normal one-task completion
instruction. Final response text is summarized and stored unchanged according to the existing
summary settings; there is no parser or fence stripping step.

## 7. Data Model Changes

- `TaskBoardSettings.allow_decompose: bool = False`.
- `TaskBoardSettings.max_subtasks: int = 5`, constrained to 2–10.
- `TaskBoardTaskOutcome` internal dataclass containing a `TaskBoardTurn | None`, failure note,
  and accepted subtasks, so the retry seam returns one named result rather than parallel values.
- `TaskBoardLimit.MIN_SUBTASKS = 2` and `TaskBoardLimit.MAX_SUBTASKS = 10`.
- A decomposition-only progress value for the isolation notice.

No checkpoint schema is expanded because decomposition is rejected when checkpointing is on.
No public result fields change; the existing `TaskBoardStepResult` represents both parent
decomposition events and child outcomes.

## 8. API Changes

### CLI

- New `run` options: `--allow-decompose/--no-allow-decompose` and `--max-subtasks 2..10`.
- `--allow-decompose` conflicts with checkpointing (the default, so callers must pass
  `--no-checkpoint`) and `--type dag`.

### SDK consumption

- Update the CLI's pinned `vidbyte-sdk[codex]` revision from the stale pre-native-tool commit to
  merged SDK main `d8483257717d6e1f99e594462b8926e9b5de525a`.
- Use only public `CodexHarnessAgentSettings.tools` and `CodexClientSettings.experimental_api`.

### Backend/network

No endpoint, capability, admission price, or payment behavior changes.

## 9. File Change Manifest

| File | Change | Why |
| --- | --- | --- |
| `docs/design/task-board-decompose-native-tool.md` | add | Record this design and verification contract. |
| `pyproject.toml` | modify | Pin the SDK revision that contains native Codex tools. |
| `src/vidbyte_cli/commands/runtime/task_board.py` | modify | Add flags, parse values, validate index-sensitive conflicts, and surface isolation. |
| `src/vidbyte_cli/lib/constants/runtime.py` | modify | Add decomposition bounds and progress copy. |
| `src/vidbyte_cli/lib/errors/failures.py` | modify | Add typed pre-admission conflict failure. |
| `src/vidbyte_cli/lib/runtime_primitives/task_board.py` | modify | Add capture/tool factory, native agent wiring, and mutable depth-one runner. |
| `src/vidbyte_cli/lib/runtime_primitives/task_board_system.md` | modify | State the native-tool task contract without fenced syntax. |
| `src/vidbyte_cli/types/runtime.py` | modify | Add settings fields and named task outcome type. |
| `scripts/test-task-board-decompose-native-tool.py` | add | Run the focused offline Section 10 verification pack. |
| `scripts/run_ci.py` | modify | Register the focused verification in the canonical source gate. |

No new source folder is required, so no folder README change is planned. Existing checkpoint,
DAG, persistence, and generic task-board verification scripts are not duplicated or rewritten.

## 10. Testing Plan

### Unit

The focused script uses fake turns at the existing session `_turn` seam and tests the real
capture, SDK tool schema, settings, prompt, and mutable-run logic. Every case has the required
risk classification:

| Case | Verification |
| --- | --- |
| default off | `[Edge Case]` Confirm settings do not register decomposition unless opted in. |
| option bounds | `[Edge Case]` Accept 2 and 10; reject 1 and 11. |
| native schema | `[Hidden Assumption]` Confirm name, required `subtasks` array, safe permission, and meaningful description. |
| native capture | `[Hidden Failure]` Confirm an accepted tool call is available after a completed turn. |
| malformed tool arguments | `[Hidden Failure]` Confirm SDK validation failure leaves the board unchanged. |
| candidate normalization | `[Silent Failure]` Confirm blanks, overlong candidates, and case-insensitive duplicates are removed in order. |
| maximum cap | `[Edge Case]` Confirm accepted candidates stop at the configured per-parent cap. |
| minimum candidate count | `[Silent Failure]` Confirm zero or one valid candidate keeps the parent whole. |
| exact splice | `[Hidden Assumption]` Confirm `[A, B, C]` with B split becomes `[A, child-1, child-2, C]` and later indices shift. |
| board ceiling | `[Edge Case]` Confirm a splice at capacity is skipped and a near-capacity splice fits without exceeding 500. |
| isolated parent | `[Silent Failure]` Confirm parent prompts contain no prior summaries. |
| isolated children | `[Hidden Assumption]` Confirm child prompts contain only their own task and no sibling/parent text. |
| depth one | `[Hidden Failure]` Confirm a child's attempted tool call cannot create grandchildren. |
| retry isolation | `[Hidden Failure]` Confirm a failed attempt's accepted capture is discarded and a successful retry splices once. |
| failed parent | `[Hidden Failure]` Confirm failure never mutates the work list. |
| plain final text | `[Edge Case]` Confirm normal final text is preserved without a parser or fence removal. |
| duplicate tool calls | `[Hidden Failure]` Confirm only the first accepted call controls the splice. |
| braces and Unicode task text | `[Hidden Assumption]` Confirm prompt rendering remains literal and does not format task content. |
| index-sensitive conflicts | `[Hidden Assumption]` Confirm DAG and checkpoint combinations fail before admission while unchecked linear mode succeeds. |

### Integration

- Run the focused script against the installed SDK native `tool` decorator and
  `CodexHarnessAgentSettings` without launching Codex.
- Run `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy src`, the
  repository lint suite, and the full `python scripts/run_ci.py` gate.
- Confirm the wheel contains `task_board_system.md` and the clean-wheel SDK import still works.

### Manual

1. With Codex credentials and a disposable workspace, run a two-task unchecked linear board with
   `--allow-decompose --no-checkpoint` and inspect that a parent can call the tool and children
   run independently.
2. Run with default checkpointing and with `--type dag`; confirm both reject before admission.
3. Run `vidbyte-cli runtime task-board run --help`; confirm native-tool flags are visible and
   normal help remains usable without starting a Codex process.

## 11. Dependencies

- Requires `vidbyte-sdk` native Codex tool support at merged revision
  `d8483257717d6e1f99e594462b8926e9b5de525a`.
- Uses existing Python 3.11, Pydantic, Click, and task-board dependencies.
- No new service, endpoint, payment, or persistent-storage dependency.

## 12. Rollout

The feature is opt-in and off by default, so existing linear, DAG, checkpoint, and resume users
retain their current behavior. The SDK pin update is required before publishing a CLI artifact;
the package gate verifies it can import the Codex facade from a clean wheel environment.

If native tool execution is unavailable at runtime, the existing task-board host failure path
applies to that attempt and normal retry/stop behavior remains authoritative. No migration is
needed because decomposition cannot write checkpoint records.

## 13. Open Questions

- Should a future version allow checkpointing by switching from positional indices to stable task
  identities? This design leaves that migration out of scope.
- Should a future tool return structured child metadata (labels, dependencies, or cost hints)?
  The first version accepts only task strings to keep the splice contract auditable.
- Should native tool call telemetry be surfaced in JSONL transitions? The current task-board
  result contract reports the decomposition event, not provider-internal tool-call events.

## 14. Alternatives

### Keep the fenced final-response protocol

Rejected because the model's answer and control message share one untyped text channel, malformed
blocks are silent, and a final-response parser duplicates the native SDK tool contract.

### Import and call the SDK's Codex bridge directly

Rejected because the bridge is an SDK implementation seam. Passing a public decorated tool through
`CodexHarnessAgentSettings` keeps provider transport and permission policy in the SDK.

### Allow decomposition with checkpoints or DAG links

Rejected because replacing a task shifts every later positional index. Supporting it would need
stable task IDs, checkpoint migration, dependency remapping, and a different resume contract.

### Let the tool mutate the board directly

Rejected because a tool callback should report a domain result, not own orchestration state. The
session decides whether a completed turn is eligible, applies retry/failure policy, and performs
the only mutation in one place.
