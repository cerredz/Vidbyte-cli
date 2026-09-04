# Design Doc: Runtime Primitives Skill

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-03
**Last Updated:** 2026-09-03

---

## 1. Overview

Add a top-level `skills/runtime_primitives/` package that teaches coding agents how Vidbyte's local runtime primitives use installed Codex and Claude Agent SDK harnesses. The skill explains the execution boundary, provider control surfaces, translation limits, safety rules, and official documentation routes without changing the current CLI scaffold or launching any agent process.

---

## 2. Goals & Non-Goals

### Goals

- Explain runtime primitives as Vidbyte-owned orchestration algorithms executed through a user's native coding-agent harness.
- Distinguish exact translations, policy translations, emulations, and unsupported controls.
- Inventory the practical control surfaces exposed by the Codex SDK/app-server and Claude Agent SDK.
- Supply more than ten described official documentation links across both providers.
- Route future implementers from one concise `SKILL.md` into focused reference files.
- Preserve the existing guarantee that the scaffold performs no paid admission or subprocess execution.

### Non-Goals

- Do not implement the runtime executor, provider adapters, paid admission, or subprocess launch.
- Do not change CLI commands, Python package behavior, or distribution dependencies.
- Do not treat direct model APIs as equivalent to provider-owned coding-agent harnesses.
- Do not promise cross-provider parity where one SDK owns or omits a capability.
- Do not add feature tests for Markdown-only guidance.

---

## 3. Background & Context

The CLI now discovers Codex, Claude, and OpenCode and constructs an inert launch plan for `runtime adversarial-team`. Its next implementation phase needs an explicit mental model: Vidbyte defines the orchestration primitive, but the selected host owns its model/tool loop, local instructions, tool implementations, context compaction, permissions, and session protocol. Adapter code can configure exposed knobs and normalize observable events; it cannot override controls the host does not expose.

Repository skills are the right durable surface for these rules because future coding agents need them while planning adapter work. A short skill entry point with progressively disclosed references keeps routine tasks concise while making the provider inventories and official sources available when needed.

---

## 4. Requirements

### Functional Requirements

1. `SKILL.md` must have valid YAML frontmatter and describe precise trigger conditions.
2. The skill must direct readers to a runtime-primitives overview before provider-specific implementation work.
3. The Codex reference must cover prompts, context, model/reasoning settings, threads, forks, structured output, tools, MCP, approvals, sandboxing, subagents, events, usage, and known ownership limits.
4. The Claude reference must cover system prompts, setting sources, sessions, forks, structured output, tools, MCP, permissions, hooks, subagents, streaming, budgets, cost, and checkpointing.
5. A translation matrix must classify each shared concept as exact, policy-based, emulated, or unavailable for each provider.
6. A documentation index must contain at least ten official links, each with a description of the page and why an adapter implementer should read it.
7. All provider-dependent statements must identify the SDK/app-server or CLI surface to which they apply.

### Non-Functional Requirements

- Keep `SKILL.md` concise and put detailed inventories in `references/`.
- Prefer official OpenAI and Anthropic documentation links.
- Do not include credentials, account-specific configuration, or hidden transcripts.
- Clearly label version-sensitive capabilities and require re-verification before implementation.
- Existing repository verification must remain green.

---

## 5. High-Level Design

The skill is a routing layer. It establishes the ownership model and sends the reader to one or more focused references. The runtime overview defines the product boundary; provider guides enumerate controls; the matrix supports architecture decisions; the documentation index is the verification trail.

```text
SKILL.md
  -> runtime-primitives.md
  -> codex-sdk.md / claude-agent-sdk.md
  -> control-matrix.md
  -> documentation-index.md
```

---

## 6. Detailed Design

### 6.1 Skill Entry Point

**File(s):** `skills/runtime_primitives/SKILL.md`
**Type:** New file

Defines triggers, mandatory reading order, architectural invariants, implementation workflow, and safe stopping conditions.

### 6.2 Runtime Primitive Model

**File(s):** `skills/runtime_primitives/references/runtime-primitives.md`
**Type:** New file

Explains product intent, local execution, Vidbyte/provider ownership, adapter responsibilities, and how multi-agent algorithms compose native harness agents.

### 6.3 Provider Control Inventories

**File(s):** `skills/runtime_primitives/references/codex-sdk.md`, `skills/runtime_primitives/references/claude-agent-sdk.md`
**Type:** New files

Documents each provider's programmable controls and explicit non-controls, including lifecycle, prompts, tools, permissions, sessions, subagents, events, and observability.

### 6.4 Translation Matrix and Documentation Index

**File(s):** `skills/runtime_primitives/references/control-matrix.md`, `skills/runtime_primitives/references/documentation-index.md`
**Type:** New files

Classifies translation quality and provides a described official-source index with more than ten links across OpenAI and Anthropic.

---

## 7. Data Model Changes

None. This change adds Markdown guidance only.

---

## 8. API Changes

None. No command, Python API, backend route, or provider process behavior changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/runtime-primitives-skill.md` | Source-of-truth design |
| CREATE | `skills/runtime_primitives/SKILL.md` | Skill trigger and workflow |
| CREATE | `skills/runtime_primitives/references/runtime-primitives.md` | Shared runtime ownership and use-case model |
| CREATE | `skills/runtime_primitives/references/codex-sdk.md` | Codex control inventory |
| CREATE | `skills/runtime_primitives/references/claude-agent-sdk.md` | Claude control inventory |
| CREATE | `skills/runtime_primitives/references/control-matrix.md` | Cross-provider translation classification |
| CREATE | `skills/runtime_primitives/references/documentation-index.md` | Described official SDK links |

Repository count: 7 files created, 0 files modified, 0 files deleted.

---

## 10. Dependencies & External Services

No package dependencies. Official OpenAI Codex and Anthropic Claude Agent SDK documentation are source references; their version-sensitive surfaces must be rechecked when adapter code is implemented.

---

## 11. Rollout & Deployment

Merge as additive developer guidance. The skill is available from the source repository and does not need runtime registration or wheel packaging. Rollback removes only the skill and its design doc.

---

## 12. Open Questions

- [ ] Should the future executor use each provider's language SDK directly or standardize on subprocess protocols where available?
- [ ] Which OpenCode SDK surface should be documented once its first adapter is scoped?
- [ ] Should runtime primitive manifests declare required provider capability levels before admission?

---

## 13. Alternatives Considered

### Alternative 1: Put Everything in README

- What: Add the complete provider inventories to the user-facing CLI README.
- Why rejected: This is implementation guidance, changes faster than the CLI command contract, and would overwhelm normal users.

### Alternative 2: One Large Skill File

- What: Put triggers, architecture, matrices, and all links in `SKILL.md`.
- Why rejected: Every invocation would consume details for both providers even when only one adapter is in scope.

### Alternative 3: Document Only Common Denominators

- What: Describe only controls shared by Codex and Claude.
- Why rejected: Runtime primitives need native strengths, and hiding provider-specific features would encourage lowest-common-denominator adapters.
