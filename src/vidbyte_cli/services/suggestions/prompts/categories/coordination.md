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

Every coordination suggestion must resolve a dependency, ownership gap, sequencing conflict, or
decision exchange between identifiable actors. The proposal should:

- Name the people, teams, agents, or systems whose work must align and the shared result they affect.
- Identify the specific decision, handoff, input, output, timing, or boundary that is currently unclear.
- Assign one accountable owner while distinguishing contributors, approvers, recipients, and observers.
- Make the next exchange concrete through a written decision, artifact, interface, checkpoint, or
  explicit commitment.
- Explain how the coordination move unlocks progress instead of adding meetings or status reporting.
- Use supplied context to identify current commitments, dependencies, blockers, and authority; label
  inferred willingness or capacity as assumptions.
- Include confirmation, escalation, and recovery paths when a dependency changes or a commitment is
  missed.
- Respect privacy, authority, workload, and the possibility that coordination can become overhead.
- Define a visible signal that the parties are aligned and the dependent work can proceed.
- Keep cross-actor alignment as the primary mechanism; route individual execution, broad strategy,
  and system bottlenecks to their focused categories.

## Candidate shape

Shape the candidate as an alignment packet that turns an implicit dependency into an explicit exchange.
The reader should know who decides, who supplies what, by when, and how the agreement is confirmed.

- In the **summary**, name the shared outcome, actors, dependency, and coordination failure to resolve.
- In the **action sequence**, surface the dependency, propose the smallest exchange, confirm ownership,
  and record the result for dependent work.
- In **decision points**, choose accountable owner, authority, sequence, response deadline, escalation,
  and what happens if information or capacity changes.
- In **considerations**, cover handoff quality, timing, incentives, communication cost, autonomy,
  trust, privacy, failure recovery, and the risk of shared-but-unowned work.
- In **dependencies**, name the artifact, decision, access, or prior commitment needed from each actor.
- In **evidence references**, cite existing commitments, blockers, interfaces, or missed handoffs; do
  not cite assumed agreement.
- In **assumptions**, label availability, authority, interpretation, and response-time assumptions and
  pair each with a confirmation step.
- In the **completion criterion**, require an explicit decision, owner, handoff, and confirmation that
  the dependent work can proceed.
- If the issue is one person's task rather than an interdependent exchange, route it elsewhere.

## Valid suggestion directions

Use this category for concrete alignment moves:

- Assign an accountable decision owner where responsibility is currently shared or unclear.
- Write a handoff packet with input, output, acceptance, deadline, and recipient.
- Resolve sequencing between dependent workstreams and record the gate that unlocks the next stage.
- Create a short written decision instead of a meeting that would only exchange status.
- Define an interface or contract between teams, agents, or systems.
- Establish a confirmation or escalation path for missed commitments.
- Align interpretation of requirements, quality, scope, or authority before execution diverges.
- Coordinate a shared resource, review window, or capacity reservation.
- Reconcile conflicting commitments with a named tradeoff and accountable choice.
- Capture a decision record so future actors do not repeat the same alignment work.

## Alignment check

The candidate is aligned when progress depends on more than one actor and the primary intervention
clarifies an ownership, decision, dependency, sequence, or handoff. A meeting is only a valid action
when it produces that explicit alignment. The suggestion must reduce ambiguity and make the next
exchange inspectable.

Reject or reroute candidates that:

- Concern one person's execution with no dependency; use immediate next steps, completion, or delegation.
- Select a broad direction that coordinates many later choices; use strategy.
- Address a single scarce system stage rather than actor alignment; use bottleneck.
- Ask for information from an authority without defining a decision or handoff; use investigation or verification.
- Add recurring communication without an ownership or sequencing problem to solve.

The primary decision must be which explicit exchange or accountable commitment allows dependent work to proceed.

## When not to use
Do not use this category when the obstacle is entirely within one person’s task or when no dependency between actors exists. Avoid it when a status meeting would only report information without resolving an ownership or sequencing mismatch. If the work needs a broader directional choice, use strategy; if one scarce stage limits everyone, use bottleneck.
