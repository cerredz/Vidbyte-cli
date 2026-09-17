# Design Doc: Suggestion Agent Message Tools

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-17
**Last Updated:** 2026-09-17

---

## 1. Overview

Add two narrowly-scoped tools to the suggestion workflow. A generator can call message_parent when it needs information from the parent agent that invoked the CLI, and an independent critic can call message_generator to send additional guidance to the persistent generator conversation. The tools are ordinary callable tools installed only on the appropriate agent, while the suggestion service owns the small run-local message state and decides what happens after a message is emitted. The message text shown to each model explicitly tells it that the call is a stop signal, explains the recipient, and asks it to provide the message before stopping.

---

## 2. Goals & Non-Goals

### Goals

- Give the generator a message_parent tool with a descriptive stop instruction.
- Give each independent critic a message_generator tool with a descriptive stop instruction.
- Deliver critic messages to the generator through its existing context manager before the next refinement turn.
- Return generator-to-parent messages in the CLI result as a bounded, typed needs_input outcome.
- Keep the tool implementations local to vidbyte-cli; do not add a new generic message API to vidbyte-sdk.
- Preserve role isolation: generator tools are never exposed to critics, and critic tools are never exposed to generators.
- Keep messages run-local, bounded, deterministic, and visible in offline verification.

### Non-Goals

- Do not make a tool callback directly invoke another model turn or re-enter CodexHarnessAgent.
- Do not add live bidirectional stdin/stdout protocol support in this change.
- Do not replace the typed critic context or structured generator output with free-form messages.
- Do not expose filesystem, command execution, network, or write authority through either message tool.
- Do not modify vidbyte-sdk; its existing callable-tool bridge is sufficient.

---

## 3. Background & Context

- The suggestion service now keeps one persistent generator session and places independent critic context into that session between refinement turns.
- The CLI's previous pinned SDK revision predates callable tools; the dependency pin moves to the current tool-capable SDK revision, which accepts callable tools through CodexHarnessAgentSettings.tools and runs them through the Codex dynamic-tool bridge.
- The generator and critic currently have separate SDK settings paths, but the suggestion adapter does not yet pass role-specific tools.
- A tool callback cannot synchronously run the external parent agent that launched the CLI. The CLI therefore records a parent request and returns it as structured output; an embedded caller can inspect the same run-local state through the service boundary in a future extension.
- Repository instructions require lazy SDK imports in services/suggestions/sdk.py, typed local boundaries, prompt assets in Markdown, final-only stdout, and the canonical scripts/run_ci.py gate.

---

## 4. Requirements

### Functional Requirements

1. The generator agent must receive exactly one additional callable tool named message_parent.
2. The critic agent must receive exactly one additional callable tool named message_generator.
3. message_parent must accept one non-empty message and return descriptive text instructing the generator that it received a stop signal, that the message is being sent to the parent agent, and that it must stop generating.
4. message_generator must accept one non-empty message and return descriptive text instructing the critic that it received a stop signal, that the message is being sent to the generator, and that it must stop reviewing.
5. A critic message must be added to the persistent generator's next context-manager update and must not directly start a nested generator turn.
6. A parent message must cause the service to return a result with status=needs_input and stop_reason=parent_message after the generator turn.
7. A message must be retained in the public result only as bounded message data; raw tool objects and callbacks must never cross the result boundary.
8. Message storage must be created per service run and must not leak messages between requests.
9. Empty, whitespace-only, overlong, malformed, or over-limit messages must be rejected by the tool boundary without mutating run state.
10. Extra-compute fan-out generator agents must not receive message_parent; only the canonical persistent generator may contact the parent.
11. Existing structured candidate, critic, context, usage, timeout, and thread-identity behavior must remain unchanged when no message tool is called.

### Non-Functional Requirements

- No new SDK provider protocol is introduced; the CLI updates its existing pinned SDK revision to the tool-capable release.
- Message calls must be safe-only tools and must not broaden the existing read-only agent sandbox.
- Message bodies and counts are bounded to prevent prompt or result amplification.
- The message path must preserve final-only stdout and existing machine-readable result envelopes.
- The service must continue to work with the existing offline fake SDK and with the SDK extra absent until a model-backed run is requested.
- The implementation must pass Ruff, strict mypy, the repository lint suite, the executable suggestion verification script, and scripts/run_ci.py.

---

## 5. High-Level Design

Add a small SuggestionMessageTools stateful collaborator under the suggestion service. It owns two bounded message collections and exposes two model-facing callable methods. The methods have distinct names, descriptions, recipients, and stop text. The collaborator is instantiated inside one SuggestionService._run invocation and is passed only to the code constructing the relevant agent settings.

Extend the local SDK adapter input with a tuple of callable tools. SuggestionSdk.agent_settings forwards that tuple into CodexHarnessAgentSettings; no SDK source changes are needed. The canonical generator session receives message_parent. The fresh critic call receives message_generator. Fan-out generators receive no messaging tool.

After a critic turn, the service drains critic messages and builds the existing replaceable critic context primitive with an additional bounded advisory section. After any generator turn, the service checks for a parent request before accepting the structured candidate artifact. A pending parent request returns a typed needs_input result carrying the message. The current one-shot CLI remains non-blocking and does not pretend it can invoke the external parent process.

~~~text
[critic turn]
    -> message_generator(message)
    -> run-local collaborator stores message
    -> critic turn completes
    -> service places critic signal + message in generator context
    -> persistent generator refinement turn

[generator turn]
    -> message_parent(message)
    -> run-local collaborator stores parent request
    -> generator turn completes
    -> service returns needs_input result to the invoking parent agent
~~~

---

## 6. Detailed Design

### 6.1 Suggestion message tool collaborator

**File(s):** src/vidbyte_cli/services/suggestions/message_tools.py
**Type:** New file

#### What it does

Stores bounded, run-local messages and exposes the two role-specific callables used by the SDK adapter. The class is the only owner of message validation, count limits, and model-facing stop descriptions.

#### Interface / API

~~~python
class SuggestionMessageTools:
    def generator_tools(self) -> tuple[Callable[..., Any], ...]: ...
    def critic_tools(self) -> tuple[Callable[..., Any], ...]: ...
    def drain_generator_messages(self) -> tuple[str, ...]: ...
    def parent_messages(self) -> tuple[str, ...]: ...
~~~

The returned callables are named message_parent and message_generator. Each accepts one message: str argument and returns a string acknowledgement containing the explicit stop instruction. The collaborator enforces a fixed maximum body length and a fixed maximum number of messages per run.

#### Logic / Algorithm

1. Construct empty parent and generator message collections for one run.
2. Validate that every body is a string containing non-whitespace content and is within the body limit.
3. Reject calls after the per-recipient message limit without appending.
4. Append valid critic messages to the generator collection and valid generator messages to the parent collection.
5. Return role-specific acknowledgement text that tells the calling model it received a stop signal, names the recipient, and tells it to stop immediately after providing the message.
6. Drain critic messages once per refinement boundary; parent messages remain available for result construction.

#### Edge Cases & Error Handling

- Empty and whitespace-only bodies return tool failures and do not mutate state.
- Bodies over the configured limit return tool failures and do not mutate state.
- A sixth message (or whichever configured maximum is reached) returns a bounded failure acknowledgement.
- The two tool names cannot collide because they are installed on separate agent catalogs; accidental same-catalog registration remains the SDK's duplicate-name error.

### 6.2 SDK adapter tool forwarding

**File(s):** src/vidbyte_cli/services/suggestions/sdk.py
**Type:** Modified

#### What it does

Adds role-independent callable tools to the strict local SuggestionAgentSettingsInput and forwards them to CodexHarnessAgentSettings while preserving the lazy SDK import boundary.

#### Interface / API

~~~python
@dataclass(frozen=True, slots=True)
class SuggestionAgentSettingsInput:
    role: Literal["generator", "critic"]
    system_prompt: str
    context: SuggestionAgentContext
    output_schema: type | Mapping[str, Any]
    provider: str | None = None
    model: str | None = None
    tools: tuple[Callable[..., Any], ...] = ()
~~~

#### Logic / Algorithm

1. Validate that tools are a tuple of callable values at the local boundary.
2. Preserve the existing provider, model, sandbox, approval, context-manager, and schema translation.
3. Include tools in the SDK settings only when non-empty.
4. Leave permission policy at the SDK default because both message tools are safe functions.

#### Edge Cases & Error Handling

- A list, non-callable value, or malformed settings object is rejected before SDK construction.
- Empty tools preserve the current no-tool path and existing fake SDK behavior.
- SDK-unavailable behavior remains unchanged because imports stay inside SuggestionSdk.load.

### 6.3 Critic context message rendering

**File(s):** src/vidbyte_cli/types/suggestions.py, src/vidbyte_cli/services/suggestions/sdk.py
**Type:** Modified

#### What it does

Carries bounded critic-to-generator messages alongside the existing typed SuggestionCriticContext and renders them as advisory, untrusted model data in the existing replaceable context primitive.

#### Interface / API

~~~python
@dataclass(frozen=True, slots=True)
class SuggestionCriticContextPrimitive:
    context: SuggestionCriticContext
    messages: tuple[str, ...] = ()
~~~

SuggestionSdk.place_critic_context continues to upsert one suggestion-critic:latest primitive at end of conversation.

#### Logic / Algorithm

1. Validate that messages are a tuple of bounded strings.
2. Render the structured critic signal exactly as before.
3. Render each message as advisory text, explicitly separate from system instructions and typed verdicts.
4. Replace the previous critic primitive so the persistent generator sees only the latest round's critic signal and messages.

#### Edge Cases & Error Handling

- No messages render an explicit none supplied line or omit only the new subsection while preserving the existing signal.
- Invalid message types fail construction before context placement.
- Messages are bounded before rendering so a tool cannot exceed the context budget through repeated calls.

### 6.4 Workflow routing and result state

**File(s):** src/vidbyte_cli/services/suggestions/service.py, src/vidbyte_cli/types/suggestions.py
**Type:** Modified

#### What it does

Creates the run-local message collaborator, gives each role only its permitted tool, places critic messages before refinement, and returns parent requests as a typed terminal result.

#### Interface / API

~~~python
class RunStatus(StrEnum):
    NEEDS_INPUT = "needs_input"


class StopReason(StrEnum):
    PARENT_MESSAGE = "parent_message"


class SuggestionResult(BaseModel):
    agent_messages: tuple[str, ...] = ()
~~~

#### Logic / Algorithm

1. Instantiate SuggestionMessageTools at the beginning of _run.
2. Pass generator_tools() only when constructing the canonical persistent generator session.
3. Pass critic_tools() only in the independent critic turn.
4. After the critic turn, drain generator messages and construct SuggestionCriticContextPrimitive(critic_context, messages).
5. After each generator turn, check parent_messages() before structured-output reconciliation.
6. If a parent message exists, return the current committed ideas plus needs_input, parent_message, and the bounded message tuple.
7. Keep normal rounds, limits, structured validation, and thread verification unchanged when no messages exist.

#### Edge Cases & Error Handling

- A critic message does not itself bypass structured critic validation; it is advisory context attached to a valid critic artifact.
- A parent message takes precedence over a subsequent schema error caused by the model attempting to stop without producing a normal artifact.
- A timeout or provider failure with no message follows the existing failure path.
- If a parent message occurs after some ideas exist, those ideas are returned as the committed partial result.

### 6.5 Prompt instructions

**File(s):** src/vidbyte_cli/services/suggestions/prompts/generator.md, src/vidbyte_cli/services/suggestions/prompts/critic.md
**Type:** Modified

#### What it does

Explains the stop-signal semantics and the exact recipient for each tool without changing the structured output contract.

#### Logic / Algorithm

1. Add a generator tool-use section stating that message_parent is only for materially missing information.
2. Add a critic tool-use section stating that message_generator is only for high-level guidance not represented by the structured critic context.
3. State that after calling the tool the model must provide its message and stop the current turn.
4. Preserve the existing identity, algorithm, prohibition, and output sections.

#### Edge Cases & Error Handling

- Prompts must not imply that the tool can execute work, grant permission, or directly invoke another model.
- Prompt wording must match the tool acknowledgement exactly enough that the model does not continue ordinary generation after a stop call.

### 6.6 Executable verification

**File(s):** scripts/test-suggestion-agent-message-tools.py, scripts/run_ci.py
**Type:** New file; Modified

#### What it does

Exercises the message collaborator and the service's fake SDK boundary, then registers the script in the canonical source gate.

#### Logic / Algorithm

1. Instantiate the tools and call each role-specific tool directly.
2. Verify role names, descriptions, stop acknowledgements, validation, and message caps.
3. Run a fake critic turn and verify its message appears in the next generator context.
4. Run a fake generator turn and verify a parent message returns needs_input with parent_message.
5. Verify no tools are attached to extra-compute fan-out agents and no messages leak between runs.
6. Print one PASS or FAIL per case and a final X/Y tests passed summary.

#### Edge Cases & Error Handling

- Every case is offline and does not require vidbyte-sdk or provider credentials.
- A failing assertion exits non-zero so the canonical gate cannot silently skip the feature.

---

## 7. Data Model Changes

### 7.1 RunStatus, StopReason, and SuggestionResult

**Change type:** Modified

~~~python
RunStatus.NEEDS_INPUT = "needs_input"
StopReason.PARENT_MESSAGE = "parent_message"
SuggestionResult.agent_messages: tuple[str, ...] = ()
~~~

**Migration strategy:**

- Forward migration: additive optional result fields and enum values; existing results remain valid.
- Rollback plan: remove the new values and omit message output; no persisted database migration exists.

### 7.2 SuggestionCriticContextPrimitive

**Change type:** Modified

~~~python
messages: tuple[str, ...] = ()
~~~

**Migration strategy:**

- Forward migration: default empty tuple preserves all existing constructors and serialized context behavior.
- Rollback plan: discard messages when constructing the primitive; no durable storage is involved.

---

## 8. API Changes

N/A - This is an in-process CLI agent-tool and result-contract change. It adds no HTTP endpoint.

### 8.1 CLI result additions

**Change type:** Modified

**Request:** No new command option.

**Response:** Existing suggestions.result responses may include:

~~~json
{
  "status": "needs_input",
  "stop_reason": "parent_message",
  "agent_messages": ["What deadline should these suggestions satisfy?"]
}
~~~

**Error cases:**

| Status | Condition |
|--------|-----------|
| Existing CLI error status | malformed tool input or tool-call limit |
| Normal provider failure status | provider failure with no pending message |
| Successful result envelope | parent message recorded and returned as needs_input |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | src/vidbyte_cli/services/suggestions/message_tools.py | Role-specific bounded message tools and run-local state |
| MODIFY | src/vidbyte_cli/services/suggestions/sdk.py | Validate and forward callable tools to SDK agent settings |
| MODIFY | src/vidbyte_cli/services/suggestions/service.py | Create, route, drain, and interpret messages in the workflow |
| MODIFY | src/vidbyte_cli/types/suggestions.py | Add critic message context and parent-message result state |
| MODIFY | src/vidbyte_cli/services/suggestions/prompts/generator.md | Describe message_parent stop semantics |
| MODIFY | src/vidbyte_cli/services/suggestions/prompts/critic.md | Describe message_generator stop semantics |
| MODIFY | pyproject.toml | Pin the existing SDK dependency to the tool-capable revision |
| CREATE | scripts/test-suggestion-agent-message-tools.py | Executable offline verification for all feature behavior |
| MODIFY | scripts/run_ci.py | Register the executable verification script as a source gate |
| CREATE | docs/design/suggestion-agent-message-tools.md | Source-of-truth architecture and test plan |

---

## 10. Testing Plan

### Unit Tests

- SuggestionMessageTools -> accepts one valid parent message and returns the exact descriptive stop acknowledgement. **[Edge Case]**
- SuggestionMessageTools -> accepts one valid critic message and routes it only to generator messages. **[Edge Case]**
- SuggestionMessageTools -> rejects empty and whitespace-only bodies without mutation. **[Edge Case]**
- SuggestionMessageTools -> rejects a body at one character over the maximum. **[Edge Case]**
- SuggestionMessageTools -> rejects the first call beyond the per-run message cap. **[Edge Case]**
- SuggestionMessageTools -> does not leak messages between two instances. **[Hidden Assumption]**
- SuggestionMessageTools -> returns a bounded failure acknowledgement when the cap is reached rather than silently dropping a message. **[Hidden Failure]**
- SuggestionCriticContextPrimitive -> renders critic messages after structured signal and preserves order. **[Silent Failure]**
- SuggestionCriticContextPrimitive -> rejects a list or non-string message tuple. **[Hidden Assumption]**
- SuggestionAgentSettingsInput -> rejects a non-tuple or non-callable tool. **[Edge Case]**
- SuggestionAgentSettingsInput -> preserves empty tools as the no-tool path. **[Silent Failure]**
- Prompt assets -> contain the recipient, stop instruction, and message handoff wording for their respective tool. **[Silent Failure]**

### Integration Tests

- Fake SDK -> generator settings contain only message_parent, while critic settings contain only message_generator. **[Hidden Failure]**
- Fake SDK -> critic tool output is placed in the persistent generator's next context update. **[Silent Failure]**
- Fake SDK -> critic messages do not invoke a nested generator turn. **[Hidden Assumption]**
- Fake SDK -> parent message returns the committed prefix with needs_input, parent_message, and agent_messages. **[Hidden Failure]**
- Fake SDK -> parent message takes precedence over a malformed normal output after the stop acknowledgement. **[Hidden Failure]**
- Fake SDK -> no-message generation and critique preserve existing completion, round, token, timeout, and thread-identity behavior. **[Silent Failure]**
- Extra-compute mode -> fan-out generators receive no messaging tools. **[Hidden Assumption]**
- Service -> a second request starts with empty message state. **[Hidden Assumption]**
- Executable script -> every case prints a labeled result and exits non-zero on failure. **[Edge Case]**

### Manual / QA Test Cases

1. Given a generator with insufficient deadline information, when it calls message_parent, then the model-facing acknowledgement says it received a stop signal and the CLI emits a machine-readable needs_input result.
2. Given a critic that notices a cross-candidate overlap, when it calls message_generator, then the next generator context contains the message and no nested model call occurred during the critic turn.
3. Given a normal run where neither tool is called, when the suggestion command completes, then the result and stdout/stderr behavior match the existing workflow.
4. Given two sequential suggestion invocations, when only the first invocation sends a message, then the second invocation contains no message.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| vidbyte-sdk | `d8483257717d6e1f99e594462b8926e9b5de525a` | Registers and executes callable dynamic tools | Provider/tool bridge shape could change; existing adapter boundary tests catch this |
| pydantic | Existing CLI dependency | Validates additive result and context contracts | Schema validation could reject a malformed fake; tests cover both typed and mapping paths |
| OpenAI Codex provider | Existing configured provider | Runs generator and critic model turns | No new provider call; messages remain local to the run |

---

## 12. Rollout & Deployment

- No feature flag is required; tools are available only inside the suggestion workflow.
- This is additive for callers that do not call either tool. Existing successful result shapes remain valid.
- Deploy the CLI code and packaged prompt assets together.
- Rollback by reverting the feature commits; no durable data or server migration requires cleanup.

---

## 13. Open Questions

- [ ] Should a future release add a live parent callback for embedded callers, or is resumable CLI output sufficient?
- [ ] Should parent messages be exposed in human output as well as machine-readable output, or remain machine-only to preserve concise terminal output?
- [ ] Should multiple critic messages be preserved in order, or should only the latest message be sent to the generator?

---

## 14. Alternatives Considered

### Alternative 1: One message_agent name with role-dependent behavior

- What: Install a tool with the same public name on both agents and vary only its closure and description.
- Why rejected: Distinct names make traces, tests, and debugging unambiguous; the roles have different recipients and stop semantics.

### Alternative 2: Directly call the generator from the critic tool

- What: Have message_generator invoke another generator model turn immediately.
- Why rejected: It re-enters the model loop during a tool callback, complicates budget accounting and thread ownership, and bypasses the service's existing critic-context boundary.

### Alternative 3: Add a generic messaging primitive to vidbyte-sdk

- What: Extend the SDK with a first-class inter-agent message API.
- Why rejected: This request is specific to the CLI suggestion workflow and can use the existing callable-tool bridge without expanding the SDK public surface.

### Alternative 4: Block the CLI waiting for an external parent reply

- What: Have message_parent write a request and synchronously wait on stdin.
- Why rejected: The current CLI is a one-shot command with a final-only stdout contract and no duplex parent protocol. Returning needs_input is explicit and resumable.
