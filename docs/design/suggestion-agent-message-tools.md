# Design Doc: Suggestion Agent Message Tools

**Status:** Implemented
**Supersedes:** PR #83 (resolved in the review-resolution PR for #83)
**Builds on:** PR #88 (single persistent generator thread, one general critic handoff)

---

## 1. Overview

The suggestion workflow has two agent roles. One persistent generator keeps a single Codex
thread for the whole run, and a fresh critic reviews each round's slate. This change gives
each role one **stop-and-message tool**:

| Tool | Held by | Recipient | Effect |
| --- | --- | --- | --- |
| `message_parent` | the persistent generator | the parent agent that started the run | ends the run with `status: needs_input` and `parent_message` set |
| `message_generator` | a critic, while the caller's budget lasts | the generator | replaces that round's structured review with the message, sent as the generator's next turn |

Both tools stop the caller's turn: once the message is recorded, the running `arun` is
cancelled, so nothing the model does after the call reaches the workflow.

## 2. Review requirements (PR #83)

1. **`--max-messages`** (comment 4049672973): the number of times the critic may message the
   generator is a CLI setting, not a module constant.
2. **SDK-native tools** (comment 4050063765): tools reach `CodexHarnessAgent` the way the SDK
   defines custom tools, as `BaseTool` subclasses with a `ToolSpec`, registered through
   `CodexHarnessAgentSettings.tools` (SDK PR #434) and run as Codex dynamic tools.
3. **Descriptions and stop semantics** (comment 4050075698): each tool has a 6–8 sentence
   description of what it does and who receives the message. Calling it stops the agent, takes
   the message string the model wrote, and puts it in the other agent's context window.

## 3. Design

### 3.1 CLI side: `services/suggestions/message_tools.py`

`SuggestionMessageTool` owns everything that is not SDK-specific: its name, its model-facing
text (loaded from packaged Markdown), message validation (non-empty, at most
`MAX_AGENT_MESSAGE_CHARS` = 2,000), the recorded message, and an `asyncio.Event` stop signal.
`deliver()` records the first valid message, sets the event, and returns the receipt text. An
invalid message raises `ValueError`, which the SDK adapter returns to the model as an error
result so it can retry. One instance serves exactly one agent.

Model-facing text lives in `services/suggestions/prompts/`:
`message_parent_tool.md`, `message_parent_argument.md`, `message_generator_tool.md`,
`message_generator_argument.md`, `message_receipt.md`, and `critic_message.md` (the
generator turn that carries a critic's message).

### 3.2 SDK side: `services/suggestions/sdk.py`

`sdk.py` stays the only module that imports the SDK. `SuggestionSdk.load()` also resolves
`BaseTool`, `ToolSpec`, `ToolParameter`, and `ToolResult` from `vidbyte.tools`.
`agent_settings()` wraps each `SuggestionMessageTool` in a small `BaseTool` subclass whose
`spec()` declares one required `message: string` parameter and whose `execute()` calls
`deliver()`. The base class is only known after the lazy import, so the subclass is built at
call time.

Codex dynamic tools require `codex.client.experimental_api=True`, which is the SDK default,
and Codex registers tools only on `thread/start`. That fits both roles: the generator's tools
are fixed when its thread starts, and each critic is a fresh agent, so a critic built after the
budget is spent simply gets no tool.

### 3.3 Workflow: `services/suggestions/service.py`

- `_arun` races `agent.arun(...)` against the tool's stop event. When the event wins, the run
  is cancelled and `_AgentMessage(message)` is raised. The message wins even if the turn also
  finished, because the call means stop. A stopped turn still counts as an agent call, with no
  tokens.
- **Parent message:** raised from any generator turn, it ends `_run` with
  `StopReason.PARENT_MESSAGE`, no ideas, and `parent_message` set. `_result` maps that to
  `RunStatus.NEEDS_INPUT`.
- **Critic message:** caught inside the round loop. The message goes into the generator's next
  turn through `critic_message.md`, so it enters the generator's native thread history the same
  way a normal review does (field guide: feedback enters the persistent thread as a turn).
- **Budget:** `messages` counts critic messages sent. A critic gets `message_generator` only
  while `messages < settings.max_messages`.

### 3.4 Setting and result

- `SuggestionSettings.max_messages: int` (0–8, default 2), `--max-messages` on
  `agents suggest run`, with help asset `max_messages.md`. The default matches the default
  round count, because each critic can send at most one message before it stops.
- `SuggestionResult.parent_message: str | None`, `RunStatus.NEEDS_INPUT`,
  `StopReason.PARENT_MESSAGE`. Human rendering prints the parent message in place of ideas.

## 4. Non-goals

- A generator-to-critic message tool. The critic already reads the whole slate every round.
- Message tools on the extra-compute per-category drafting agents, which are single-turn.
- Budgeting `message_parent`, which ends the run and so happens at most once.

## 5. Verification

- `python scripts/test-suggestion-agent-message-tools.py`: the real SDK translator registers
  each tool with its authored description and one required argument. Invalid calls return
  errors. It also checks parent and critic stop paths with turn cancellation, message routing
  into the generator's next turn, the budget at `max_messages=1` and `0`, and CLI bounds.
- `python scripts/run_ci.py`: the canonical gate, which now includes the script above.
- The SDK pin moves to `d8483257` (SDK PR #434), the first revision whose
  `CodexHarnessAgentSettings` accepts `tools`.
