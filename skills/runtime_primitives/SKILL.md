---
name: runtime-primitives
description: Guides design and implementation of Vidbyte CLI runtime primitives that execute through local Codex or Claude harnesses. Use when planning provider adapters, choosing SDK controls, mapping shared abstractions, or reviewing local runtime safety and capability requirements.
---

# Runtime Primitives

Runtime primitives are Vidbyte orchestration algorithms executed through a user's installed coding-agent harness. The CLI handles discovery, admission, launch planning, orchestration, and normalized results; Codex or Claude owns its internal model/tool loop.

## Reading order

1. Always read [references/runtime-primitives.md](references/runtime-primitives.md).
2. Read the relevant provider inventory: [Codex](references/codex-sdk.md) or [Claude Agent SDK](references/claude-agent-sdk.md).
3. Read [references/control-matrix.md](references/control-matrix.md) before promising feature parity.
4. Use [references/documentation-index.md](references/documentation-index.md) to verify version-sensitive implementation details against official sources.

## Workflow

1. Write the primitive's provider-neutral requirements: topology, roles, task/result contract, budgets, cancellation, and acceptance criteria.
2. Declare required host capabilities before admission or launch.
3. Classify each mapping as exact, policy-based, emulated, or unsupported.
4. Keep provider configuration, transport, input translation, event translation, and failures behind separate collaborators.
5. Prefer native resume, fork, subagent, permission, and interruption operations.
6. Reject missing capabilities early. Never silently discard a requested control.
7. Keep credentials, raw environment values, repository contents, and hidden reasoning out of admission payloads and normalized metadata.

## Architectural invariant

Vidbyte can configure and compose public SDK controls; it cannot take ownership of provider-internal reasoning, compaction, tool implementations, model routing, account entitlements, or safety enforcement. A shared name does not imply shared semantics—document provider policy at every non-exact translation.
