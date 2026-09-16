# Bottleneck

## Description
A bottleneck suggestion targets the constraint that limits useful progress through a system. The constraint may be a person, decision, dependency, resource, queue, capability, or policy. It is not enough to identify the busiest or most visible part of the work. The suggestion should connect the constraint to a measurable loss of throughput, quality, or decision speed. Improving a non-limiting area can create activity without creating progress and may move the constraint elsewhere. Use this category when relieving one specific constraint is likely to improve the whole flow.

## Why use / use cases
- [ ] **Work is piling up at one point.** A queue, review stage, handoff, or approval step may be limiting everything downstream. Use this category when the accumulation is persistent and its effect can be observed.
- [ ] **Many people are waiting on one decision.** A delayed choice can block otherwise ready work and consume coordination energy. Suggest bottleneck relief when clarifying ownership or decision criteria would release several dependent actions.
- [ ] **A scarce skill controls the pace.** One person or capability may be required for too many tasks. Use this category when load balancing, training, tooling, or sequencing can expand effective capacity at that constraint.
- [ ] **A dependency repeatedly interrupts flow.** External systems, suppliers, permissions, or data may cause the same work to stop and restart. Recommend relief when changing the dependency interface or buffer would improve end-to-end progress.
- [ ] **Quality rework consumes the throughput.** Defects or unclear inputs may send work back through an already constrained stage. Use this category when improving the constraint’s input quality is more useful than asking it to work faster.
- [ ] **Local optimization is hiding system loss.** A team may be improving its own output while downstream work remains blocked. Suggest a bottleneck action when the system-level constraint explains the mismatch.
- [ ] **The limiting resource is changing.** A temporary surge, new project, or seasonal demand may create a new constraint. Use this category to identify the current limiter and avoid optimizing yesterday’s bottleneck.
- [ ] **One small intervention could unlock several tasks.** A template, decision, access grant, or capacity shift may release a broad queue. Recommend it when the leverage follows a traceable dependency chain rather than optimism.

## Things to consider
- Where does work wait, stop, or return most often?
- What evidence shows this point limits end-to-end progress?
- Is the constraint capacity, policy, information, quality, ownership, or dependency access?
- What downstream work is actually released if it improves?
- Would increasing input worsen the queue or rework at the constraint?
- What is the smallest intervention that changes effective capacity?
- How might relieving this constraint expose a new one?
- Which flow measure should improve and over what observation window?

## Generation requirements

Every bottleneck suggestion must identify the limiting point whose movement would change downstream
flow, quality, or completion. The proposal should:

- Name the system, workflow, or outcome being constrained and the observable flow that matters.
- Distinguish the governing constraint from a visible inconvenience, symptom, queue, or downstream
  consequence.
- Explain how the limiting point reduces throughput, quality, learning, or decision speed.
- Identify whether the constraint is capacity, dependency, policy, skill, decision, resource, or
  repeated failure.
- Use supplied observations, delays, queues, failure rates, or ownership evidence; label inferred
  causes as assumptions.
- Propose a proportionate intervention that increases flow without merely moving the queue elsewhere.
- Account for quality, safety, workload, and the possibility that relief creates a new bottleneck.
- Define the measure and observation window that would show the constraint moved.
- Include a fallback if the intervention reveals the presumed constraint was not governing.
- Keep system-level constraint relief as the primary mechanism; route priority conflicts, prerequisites,
  and stopping decisions to their focused categories.

## Candidate shape

Shape the candidate as a constraint hypothesis with a causal chain from limiting point to downstream
result. The proposal should tell an executor what to observe, what to change, and how to find the next
constraint after relief.

- In the **summary**, name the constrained outcome, suspected bottleneck, and downstream effect.
- In the **action sequence**, measure the flow, confirm the limiting point, apply a bounded relief,
  and observe whether throughput or quality changes.
- In **decision points**, choose which constraint to address, how much capacity or authority to add,
  and when to stop if the queue moves elsewhere.
- In **considerations**, cover utilization, wait time, quality, dependency, handoff, safety,
  ownership, cost, and displacement of work.
- In **dependencies**, name the data, owner, decision authority, capability, resource, or partner
  required to alter the constraint.
- In **evidence references**, cite repeated observations of delay, queue, failure, or capacity;
  do not treat one frustrating incident as a system bottleneck.
- In **assumptions**, label the causal link and pair it with a measurement or small intervention.
- In the **completion criterion**, require evidence that the target flow improved or that the
  diagnosis changed to a different limiting point.
- If no repeated constraint can be observed, recommend investigation or verification first.

## Valid suggestion directions

Use this category for moves that increase the flow through a limiting point:

- Remove a repeated approval, handoff, queue, or decision delay.
- Add capacity, automation, skill, or tooling at the stage that governs throughput.
- Protect a scarce resource from interruptions or competing work.
- Resolve a dependency that repeatedly stalls a downstream stage.
- Reduce rework or failure at the constraint instead of optimizing unconstrained work.
- Change batch size, sequence, or work-in-progress limits around the bottleneck.
- Make ownership or escalation explicit where unresolved decisions block flow.
- Measure whether relieving one constraint exposes the next governing constraint.
- Stop or defer low-value work that consumes the scarce stage.
- Improve quality at the limiting point when speed alone would amplify failure.

## Alignment check

The candidate is aligned when relieving one repeated limiting point is expected to improve a larger
flow, outcome, or quality measure. It must explain why this point governs progress and how relief will
be observed. A list of slow tasks is not a bottleneck diagnosis unless one constraint has a downstream
effect.

Reject or reroute candidates that:

- Address one isolated claim or incident with no repeated flow effect; use verification or risk prevention.
- Choose among competing commitments without a governing stage; use prioritization.
- Name a condition required before work can begin; use prerequisite.
- Improve a local experience without showing system-level constraint relief; use product experience or simplification.
- Recommend abandoning work because relief is not worth the cost; use stop or defer.

The primary decision must be whether moving this constraint changes the system rather than merely making
one task feel easier.

## When not to use
Do not use this category when the problem is a single unverified claim, an unclear goal, or a one-off unfinished task. Avoid it when no repeated constraint or system-level effect can be shown. If several commitments compete for attention, use prioritization; if the work should stop because the constraint is not worth relieving, use stop or defer.
