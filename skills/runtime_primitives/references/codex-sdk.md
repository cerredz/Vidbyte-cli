# Codex SDK and App-Server Controls

## Integration boundary

Use the official Codex SDK when available and consult app-server documentation for the underlying protocol. A Codex harness is a complete agent loop—not a model provider—so Vidbyte should orchestrate threads and normalize results around that loop.

## What the implementation can control

| Area | Practical controls |
|---|---|
| Process/client | Local app-server launch/configuration, working directory, connection lifetime, cancellation, and typed failures. |
| Thread | Start, resume, fork, persistence/ephemeral policy, and other lifecycle operations present in the reviewed SDK. |
| Turn | Prompt input, output JSON Schema, execution/cancellation methods, and observable turn items/events. |
| Prompting | Developer instructions; bounded additional context rendered into the turn when the stable SDK has no dedicated field. |
| Model | Model id, reasoning effort/summary, personality, service tier, and supported provider configuration. |
| Security | Approval mode, sandbox mode, working directory, network/config policy surfaced by Codex. |
| Multi-agent | Enablement, concurrency, default subagent model/effort, interruption messages, custom agent definitions, and collaboration activity. |
| Extensions | MCP server configuration, skills, hooks, rules, and AGENTS.md/config loading where intentionally enabled. |
| Observability | Thread/turn ids, status, duration, usage, typed item/event stream, diffs/tool calls that the public protocol exposes. |

## What the implementation cannot control

- Undocumented internal iteration ordering, hidden reasoning, compaction heuristics, or built-in tool implementations.
- The model's decision to delegate, exact subagent strategy, or deterministic completion path.
- Provider model availability, safety enforcement, rate limits, authentication, subscription entitlement, or billing policy.
- General Vidbyte middleware semantics inside Codex. Each hook/event needs an explicit mapping and failure policy.
- A monetary cap merely by setting service tier, or a universal max-iterations guarantee without a supported Codex field.

## Adapter guidance

Use native thread operations for continuation and forks. Pass structured-output schemas to the turn and validate again locally. Keep configuration translation separate from transport enum construction so importing Vidbyte does not require Codex. Serialize a bounded, reviewed subset of events and never copy reasoning item contents. Capability-check SDK/version-specific operations before admission.

See the [documentation index](documentation-index.md#codex-and-openai) for the reviewed official pages.
