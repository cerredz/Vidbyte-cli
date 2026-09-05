---
name: runtime-primitives
description: What a Vidbyte runtime primitive is, why it executes on the caller's machine instead of ours, and the shape every one of them shares. Read before adding a primitive to vidbyte-cli or changing an existing one.
---

# Runtime Primitives

A runtime primitive is a multi-agent topology that runs **on the caller's own machine**, using
a native coding agent they already installed and already pay for, while Vidbyte charges a small
admission fee for the orchestration. `same-host-ensemble` is the first implemented one;
`adversarial-team` is scaffolded and not yet built.

## Why execution is local

This is the decision everything else follows from, so it is worth being precise about.

A hosted agent needs us to run the model, hold the code, and carry the compute cost. A local
primitive needs none of that. The user's Codex or Claude subscription pays for inference, their
machine supplies the CPU, and their working directory never leaves it. What Vidbyte sells is the
topology — knowing that three decorrelated read-only proposals plus one write-enabled
implementer beats one agent, and having that wired correctly.

Three consequences that shape every primitive:

- **We never see the task, the code, or the output.** Admission carries only the host name and a
  client runtime version. If you find yourself wanting to send task text to the backend for any
  reason, you have left the model.
- **We cannot retry on the user's behalf.** There is no server-side run to resume. Failure
  handling belongs in the CLI, and partial results must be reported rather than discarded.
- **The price is per admission, not per token.** A primitive that costs two cents to admit may
  burn far more of the user's own subscription. Say so in the docs; do not hide it.

## The shape every primitive shares

Read `src/vidbyte_cli/services/ensemble/` for the worked example. Every primitive has these
seven parts, in this order:

1. **A validated input contract.** One frozen Pydantic model holding every caller-settable
   option, with bounds on the model rather than only on the Click decorator. Bounds on the model
   hold for any caller; bounds on Click hold only for the terminal.
2. **A closed host enum.** Not a string. A primitive supports a host only when an adapter for it
   actually exists and that host's fork and sandbox behavior is verified. One member is a
   perfectly good enum.
3. **A local launch plan.** Host discovery on PATH, working-directory validation, task bounds.
   All free, all before payment.
4. **A dependency check.** The SDK integration must be importable *before* admission is
   requested, so an unmet dependency costs nothing.
5. **Admission, once.** One idempotency-keyed purchase. After this point the caller has paid, so
   everything downstream must either produce a result or explain precisely what happened.
6. **The algorithm.** This should be small. If it is not small, the primitive is probably doing
   something the SDK should be doing.
7. **A normalized result.** Every branch of the topology represented, including the ones that
   failed, plus any thread ids that would let a caller resume or audit afterward.

## Ordering rules that are not negotiable

- **Free checks precede paid ones.** Input validation, SDK availability, and host discovery all
  run before admission. A user with no Codex installed must never be charged.
- **Sandbox is set explicitly, never inherited.** See the `codex-harness-sdk` skill: the
  provider-default sentinel is stripped before the SDK call, so an unset sandbox silently
  inherits the user's own configuration.
- **Exactly one agent may write.** In any topology mixing analysis with implementation, the
  analysis agents are read-only and one agent writes. Enforce it with sandbox settings, not with
  prompt instructions — a prompt is a request, a sandbox is a guarantee.
- **Partial success is reported, not discarded.** Two proposals out of three still beats one
  agent. Only an empty result set should abort.

## Where the code lives

- `src/vidbyte_cli/services/<primitive>/` — the algorithm. May import `lib/` and `types/`.
- `src/vidbyte_cli/commands/runtime/<primitive>.py` — parsing and rendering only.
- `src/vidbyte_cli/types/<primitive>.py` — the contracts.
- `src/vidbyte_cli/lib/` — shared substrate. **Nothing here may import a service.**

The direction is one way: commands depend on services, services depend on `lib/`. A service
reaching back into a command, or `lib/` reaching forward into a service, is a layering bug even
when it type-checks.

## Related

- `skills/harnesses/codex-harness-sdk/SKILL.md` — how to drive the agent, and the four things
  the SDK's merged code does that its design doc does not tell you.
- `skills/harnesses/x402-runtime-economics/SKILL.md` — admission, pricing, and what the backend
  is allowed to know.
