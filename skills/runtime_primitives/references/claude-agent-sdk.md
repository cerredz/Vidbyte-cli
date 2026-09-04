# Claude Agent SDK Controls

## Integration boundary

The Claude Agent SDK packages the Claude Code loop as Python and TypeScript libraries. Use `query()` for intentionally one-shot work and `ClaudeSDKClient` for continuous conversations, streaming input, interrupts, and explicit connection ownership. Do not confuse this SDK with the direct Messages Client SDK or hosted Managed Agents.

## What the implementation can control

| Area | Practical controls |
|---|---|
| Client/session | One-shot or connected mode, continue/resume, session fork, persistence, custom transport, and interruption. |
| Input | String or streaming input, system prompt/preset, appended system prompt, setting sources, working/additional directories. |
| Model/reasoning | Model, fallback model, effort/thinking settings, betas, and supported output styles. |
| Bounds | Maximum turns, maximum budget, task budgets, timeouts, and cancellation/interruption. |
| Output | Typed message stream, partial assistant events, result, JSON Schema structured output, usage, duration, cost, and rate-limit events. |
| Tools/MCP | Built-in tool allow/deny, in-process SDK MCP tools, external stdio/SSE/HTTP MCP servers, strict config, and tool search. |
| Permissions | Permission mode, `can_use_tool`, permission updates, approval prompts, and user-input handling. |
| Hooks | Prompt, pre/post tool, failure, stop, subagent, compaction, notification, and permission-request callbacks exposed by the SDK. |
| Subagents | Programmatic definitions with role prompt, model, tools, skills, and MCP plus progress/activity events. |
| Host features | Skills, plugins, commands, CLAUDE.md memory, file checkpoints/rewind, todos, settings, and OpenTelemetry. |

## What the implementation cannot control

- Hidden reasoning, built-in compaction algorithms, internal tool code, or model-side delegation decisions.
- Provider account/authentication policy, rate limits, model availability, entitlements, or server-side safety.
- Exact repository-instruction placement when Claude Code setting sources are loaded.
- Universal equivalence between Claude hooks and Vidbyte middleware; event timing, output capabilities, and failures differ.
- Portable session identity across providers; retain the Claude session id only as opaque provider state.

## Adapter guidance

Declare `setting_sources` explicitly instead of assuming filesystem configuration. Use native resume/fork semantics and capture the session id only after a successful result. Treat permission callbacks as a narrowing boundary and default to deny when translation is unclear. Normalize typed messages without persisting thinking blocks. Capability-check features and installed versions before paid admission.

See the [documentation index](documentation-index.md#claude-agent-sdk) for the reviewed official pages.
