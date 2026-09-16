# Coordination

## Description
A coordination suggestion aligns people, ownership, timing, or dependencies so related work can proceed together. It addresses friction created by interfaces between actors rather than the internal quality of one person’s task. The suggestion should identify the parties, shared outcome, and specific mismatch. It should prefer a clear decision, owner, or handoff over more status communication. Coordination is useful when progress depends on synchronized action or an explicit agreement. It should not create meetings or process unless they resolve a named coordination failure.

## Why use / use cases
- [ ] **Two owners assume the other will act.** An unassigned boundary can leave a task waiting without anyone seeing it as theirs. Use this category to establish one accountable owner and the inputs they receive.
- [ ] **A dependency has no agreed timing.** Related work may be individually ready but sequenced poorly. Suggest coordination when a date, trigger, or service expectation would let both sides plan reliably.
- [ ] **A handoff loses information.** Work may cross teams or tools with unclear context, acceptance, or responsibility. Use it to define the smallest handoff contract that preserves the needed information.
- [ ] **Several groups optimize conflicting outcomes.** Local goals can create delay, duplicated work, or incompatible decisions. Recommend coordination when a shared outcome or explicit tradeoff can align the groups.
- [ ] **A decision needs the right participants once.** The issue may be blocked because authority, expertise, or affected parties are missing. Use this category to arrange a focused decision with a named outcome rather than a recurring meeting.
- [ ] **Parallel work is creating collision risk.** Independent actions may modify the same resource, assumption, or interface. Suggest coordination when a boundary, lock, sequence, or shared record can prevent interference.
- [ ] **An external party controls the next step.** A supplier, partner, reviewer, or platform may need to provide something specific. Use it when the request, owner, and escalation path can be made explicit.
- [ ] **A commitment changed without downstream alignment.** New scope, timing, or constraints may invalidate assumptions held by others. Recommend a coordination action when notifying and renegotiating the affected boundary will restore a workable plan.

## Things to consider
- Which actors or systems must coordinate, and what shared outcome connects them?
- What exact mismatch exists in ownership, timing, dependency, authority, or information?
- Who is accountable after the coordination action?
- What input and acceptance condition define the handoff?
- Which decision-maker has authority to resolve the conflict?
- What is the smallest synchronization point that releases work?
- How will the agreement be recorded and made visible to affected parties?
- What happens if one party misses the commitment or the dependency changes?

## Generation requirements

Every coordination suggestion must resolve a dependency, ownership gap, sequencing conflict, or decision
exchange between identifiable actors. The category exists because some work is blocked not by anyone's
task being done badly but by the space between tasks: nobody owns the decision, two parties are waiting
on each other, an interface was never agreed, or a handoff has no defined shape. Diagnosing that space
is the first requirement — the proposal must name the actors, the shared result they affect, and the
precise mismatch, because "better communication" is not a mismatch. The preferred remedy is a decision,
an owner, an artifact, or a commitment rather than more status flow; recurring meetings are the default
response to coordination pain and usually convert a one-time ambiguity into permanent overhead. Because
commitments between actors fail, the proposal has to say what happens when one is missed. The proposal
should:

- Name the people, teams, agents, or systems whose work must align and the shared result they affect.
- Identify the specific decision, handoff, input, output, timing, or boundary that is currently unclear.
- Assign one accountable owner while distinguishing contributors, approvers, recipients, and observers.
- Make the next exchange concrete through a written decision, artifact, interface, checkpoint, or
  explicit commitment.
- Explain how the coordination move unlocks progress instead of adding meetings or status reporting.
- Include confirmation, escalation, and recovery paths when a dependency changes or a commitment is
  missed.
- Respect privacy, authority, workload, and the possibility that coordination can become overhead.
- Define a visible signal that the parties are aligned and the dependent work can proceed.
- Prefer a mechanism that expires or dissolves once the mismatch is resolved.

## Alignment check

Alignment, for coordination, means the candidate fixes an interface between actors rather than the
quality of anyone's own work. Progress depends on more than one party, and something between them is
undefined: who decides, who owns it, what one side owes the other, in what order, by when. An aligned
candidate names those parties and the shared outcome, states the specific mismatch, and proposes an
exchange concrete enough to inspect — a written decision, an owner, an agreed interface, a checkpoint, a
commitment with a date. A meeting qualifies only when the meeting produces that artifact. If the
candidate would leave the same ambiguity in place afterwards, it has not coordinated anything.

The second half of alignment is proportionality. Coordination mechanisms are easy to add and hard to
remove, so an aligned candidate reduces ambiguity without installing permanent process, and it says how
the arrangement recovers when a commitment is missed. One person's execution with no dependency belongs
to immediate next steps, completion, or delegation; a broad direction that governs many later choices
belongs to strategy; a single scarce stage in a system rather than a misalignment between actors belongs
to bottleneck; and a request for information with no decision or handoff attached belongs to
investigation or verification. Keep the candidate here only when the live question is which explicit
exchange or accountable commitment lets dependent work proceed.

## When not to use
Do not use this category when the obstacle is entirely within one person’s task or when no dependency between actors exists. Avoid it when a status meeting would only report information without resolving an ownership or sequencing mismatch. If the work needs a broader directional choice, use strategy; if one scarce stage limits everyone, use bottleneck.
