# Official SDK Documentation Index

These pages are the implementation verification trail. Provider surfaces change; re-open the relevant page before adding or widening an adapter control.

## Codex and OpenAI

1. [Codex SDK](https://developers.openai.com/codex/sdk) — SDK installation, stable language surfaces, thread creation/resumption, turn execution, streaming, and structured output. Start here when selecting the supported package and core client API.
2. [Codex App Server](https://developers.openai.com/codex/app-server) — JSON-RPC lifecycle, thread/turn methods, event notifications, approvals, and protocol types beneath the SDK. Use it to understand capabilities not yet wrapped by a language SDK.
3. [Codex subagents](https://developers.openai.com/codex/subagents) — built-in delegation, custom agent definitions, concurrency, model/effort defaults, and activity semantics. Read before mapping Vidbyte teams or child-agent metadata.
4. [Codex hooks](https://developers.openai.com/codex/hooks) — lifecycle hook events, configuration, inputs/outputs, execution constraints, and failure behavior. Use for event-by-event middleware translation design.
5. [Codex MCP](https://developers.openai.com/codex/mcp) — configuring local and remote MCP servers and exposing Codex as an MCP server. Read before translating Vidbyte tools or external integrations.
6. [Codex configuration reference](https://developers.openai.com/codex/config-reference) — exhaustive configuration keys, types, scopes, and defaults. This is the authority for model, reasoning, sandbox, approval, agent, feature, and transport settings.
7. [Codex security](https://developers.openai.com/codex/security) — threat model, sandboxing, approvals, and safe operating guidance. Read before any primitive can write files, run commands, or use network access.
8. [Codex authentication](https://developers.openai.com/codex/auth) — supported sign-in and API-key flows plus credential storage considerations. Use to preserve the user's native entitlement without copying credentials into Vidbyte.
9. [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive) — `codex exec`, machine-readable output, resume, schema output, and automation flags. Use when an SDK operation must fall back to a reviewed subprocess contract.
10. [Codex skills](https://developers.openai.com/codex/skills) — skill discovery, folder structure, trigger metadata, and repository/user scope. Read when deciding whether a runtime role should load native skills.

## Claude Agent SDK

11. [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — product boundary, supported languages, available Claude Code capabilities, authentication constraints, and comparison with the CLI, Client SDK, and Managed Agents.
12. [Claude Agent SDK Python reference](https://platform.claude.com/docs/en/agent-sdk/python) — complete `query()`, `ClaudeSDKClient`, option, message, hook, tool, MCP, permission, sandbox, and error types. This is the primary Python adapter contract.
13. [Claude Agent SDK sessions](https://platform.claude.com/docs/en/agent-sdk/sessions) — continuation, resume, fork, persisted session discovery, and session identity. Read before implementing durable state or branch lineage.
14. [Claude Agent SDK subagents](https://platform.claude.com/docs/en/agent-sdk/subagents) — programmatic role definitions, prompts, models, tools, skills, MCP access, and subagent event behavior. Read before translating Vidbyte team members.
15. [Claude Agent SDK hooks](https://platform.claude.com/docs/en/agent-sdk/hooks) — prompt, tool, stop, subagent, compaction, notification, and permission lifecycle callbacks. Use to decide whether a Vidbyte middleware rule has a faithful event mapping.
16. [Claude Agent SDK permissions](https://platform.claude.com/docs/en/agent-sdk/permissions) — permission modes, tool callbacks, approval interaction, and policy updates. Read before admitting any primitive with filesystem, shell, or network effects.
17. [Claude Agent SDK MCP](https://platform.claude.com/docs/en/agent-sdk/mcp) — in-process custom tools and external stdio/SSE/HTTP MCP server configuration. Use when translating shared tools and provider-specific server authentication.
18. [Claude Agent SDK structured outputs](https://platform.claude.com/docs/en/agent-sdk/structured-outputs) — JSON Schema configuration, result delivery, validation patterns, and failure cases. Read before mapping Vidbyte output contracts.
19. [Claude Agent SDK streaming output](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — typed messages, partial assistant events, accumulation, and final-result handling. Use when defining normalized progress/event streams.
20. [Claude Code CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage) — print mode, JSON/stream JSON, resume/continue, model, maximum turns, permissions, and tool flags. Use only for a deliberate subprocess fallback or host diagnostics.

## Source-selection rule

Prefer these official pages over blog posts or remembered SDK signatures. Inspect the installed package types as a second source when implementing a pinned version. If documentation and installed types disagree, narrow the adapter and record the compatibility decision rather than guessing.
