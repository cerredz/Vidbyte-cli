# Cross-Provider Control Matrix

Legend: **Exact** = documented native field/operation; **Policy** = similar outcome with provider-specific rules; **Emulated** = behavior outside the native loop; **No** = no reliable public equivalent promised.

| Vidbyte requirement | Codex | Claude Agent SDK | Runtime rule |
|---|---|---|---|
| System prompt | Exact: developer instructions | Exact: system prompt/preset | Define precedence with repository settings. |
| Additional context | Emulated turn block on current stable Python SDK | Exact/policy through input or appended prompt | Bound and label placement. |
| Structured output | Exact schema on turn | Exact output format | Validate locally after return. |
| Continuation | Exact thread resume | Exact client/session resume | Persist opaque id after success. |
| Fork | Exact thread fork | Exact session fork | Never synthesize lineage by copying text. |
| Context primitives | Policy: deterministic rendering | Policy: input/config rendering | Preserve content, not unsupported placement semantics. |
| Custom tools | Policy through MCP/config/app-server | Exact SDK MCP tools | Separate provider tool translators. |
| MCP | Exact provider configuration | Exact SDK configuration | Preserve transport/auth differences. |
| Tool allow/deny | Policy via approval/sandbox/config | Exact lists and callback | Shared policy can only narrow access. |
| Middleware/hooks | Policy, event-specific | Policy, event-specific | Map every event and failure mode separately. |
| Maximum turns | No universal exact mapping promised | Exact | Reject primitives requiring it on unsupported hosts. |
| Monetary budget | No equivalent assumed | Exact max-budget controls | Do not reinterpret service tier as budget. |
| Sandbox | Exact native modes/config | Exact native settings | Keep native semantics; names alone are insufficient. |
| Approval callback | Policy through approval protocol | Exact callback/input flow | Uncertain decisions default to deny. |
| Subagent definitions | Exact provider config/files | Exact programmatic definitions | Retain provider-specific role controls. |
| Delegation choice | Provider-owned | Provider-owned | Observe, never promise deterministic selection. |
| Usage/cost | Usage exact when returned; cost separate | Usage and cost fields exposed | Mark missing fields and pricing provenance. |
| Event streaming | App-server exact; SDK coverage varies | Exact typed async stream | Normalize stable event subset. |
| Compaction | Provider-owned | Provider-owned plus hooks | Do not inject Vidbyte compaction into native loop. |
| Checkpoint/rewind | Verify reviewed app-server version | Exact documented feature | Capability-check before use. |
| Hidden reasoning | No | No | Never collect or expose. |
| Vidbyte model middleware | No direct parity | No direct parity | Keep outside provider loop or reject. |

## Pre-launch checklist

- [ ] Record provider SDK and executable versions.
- [ ] Resolve required capabilities before admission.
- [ ] Classify every public setting using the legend.
- [ ] Specify settings precedence and repository-config loading.
- [ ] Specify cancellation, cleanup, retries, and session ownership.
- [ ] Specify permission-denial and approval behavior.
- [ ] Bound event/result metadata and exclude credentials/reasoning.
- [ ] Use native resume/fork lineage.
- [ ] Reject all unsupported primitive requirements.
