# Runtime Primitives

## Intended use

A runtime primitive packages a reusable multi-agent or agent-control algorithm—such as adversarial review, debate, evaluator-optimizer, fan-out/fan-in, or search—and runs it locally through native coding agents. The user's host retains repository access, instructions, MCP servers, tools, skills, permission policy, and model subscription.

```text
vidbyte-cli primitive
  -> authenticate and admit the algorithm
  -> inspect host capability and create safe launch plan
  -> construct CodexHarnessAgent / ClaudeHarnessAgent instances
  -> coordinate roles and messages
  -> normalize evidence, usage, status, and final result
```

## Ownership

Vidbyte owns primitive identity/version, roles, task graph, routing, cross-agent message envelopes, retries around whole provider operations, aggregate acceptance criteria, admission, and result presentation. The native host owns each agent's internal model/tool iterations, built-in tool behavior, context compaction, sandbox enforcement, provider events, and session storage.

The adapter is a translation boundary, not a replacement loop. It should expose a Vidbyte-shaped run/resume/fork/result surface while keeping provider-only controls in a typed settings object.

## Translation categories

- **Exact:** direct documented SDK field or operation with matching semantics.
- **Policy-based:** similar outcome composed from provider-specific controls; precedence and failure semantics must be explicit.
- **Emulated:** behavior implemented outside the native loop; must not be advertised as native equivalence.
- **Unsupported:** no dependable public surface; reject the primitive requirement before charging or launch.

## Capability admission

A future primitive manifest should declare requirements such as native fork, structured output, subagents, permission callbacks, event streaming, spend/turn bounds, or checkpoints. Host discovery alone is insufficient: an installed executable may be too old or its selected SDK surface may lack the required control. Resolve version and capability before requesting paid admission.

## Security rules

- Execute in the intended working directory, but never upload repository contents for admission.
- Inherit the local environment only inside the child process; never serialize it into logs, metadata, or API requests.
- Let provider-native sandbox and approval policy remain authoritative. Vidbyte may impose stricter rules, never weaker ones.
- Treat session/thread IDs as opaque provider state and redact tokens, auth files, tool results, and private reasoning.
- Stop before side effects when adapter compatibility or primitive capability requirements are uncertain.
