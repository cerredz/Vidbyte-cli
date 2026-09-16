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
flow, quality, or completion. The category exists because effort spent anywhere other than the
constraint produces activity rather than progress, and that distinction is invisible from inside a busy
system. The first requirement is therefore diagnostic: the proposal must separate the point that
governs the flow from the point that is most visible, most complained about, or most overloaded, which
are frequently different things. It then has to say what kind of constraint it is — capacity,
dependency, policy, skill, decision authority, resource, or a repeated failure — because the class
determines what relief is even possible. Relief must be proportionate to the constraint, and the
proposal has to anticipate where the constraint will move once this one is relieved, since a system
always has a next limiting point. Because a constraint diagnosis can be wrong, the suggestion needs an
observable signal that would confirm or refute it. The proposal should:

- Name the system, workflow, or outcome being constrained and the observable flow that matters.
- Distinguish the governing constraint from a visible inconvenience, symptom, queue, or downstream
  consequence.
- Explain how the limiting point reduces throughput, quality, learning, or decision speed.
- Identify whether the constraint is capacity, dependency, policy, skill, decision, resource, or
  repeated failure.
- Propose a proportionate intervention that increases flow rather than merely moving the queue
  elsewhere.
- Account for quality, safety, workload, and the possibility that relief creates a new bottleneck.
- Define the measure and observation window that would show the constraint moved.
- Include a fallback if the intervention reveals the presumed constraint was not governing.
- Name who owns the limiting point, since a constraint nobody owns cannot be relieved by a suggestion.

## Alignment check

Alignment, for bottleneck, means the candidate acts on the one point that governs how much useful work
gets through. Every system has a slowest stage, and until that stage moves, improvements anywhere else
accumulate as inventory rather than as output. An aligned candidate therefore argues that a specific
point is governing — that work waits on it, that quality or decision speed degrades because of it, that
relieving it would be felt downstream — and proposes relief sized to that constraint. Naming a slow or
unpleasant task is not a diagnosis. The candidate has to connect the limiting point to a downstream
effect the caller can observe.

The second half of alignment is system thinking. Relief moves the constraint rather than removing it,
so an aligned candidate says where the next limiting point is expected to appear and what would show
the intervention worked. A single isolated claim or incident with no repeated flow effect belongs to
verification or risk prevention; a conflict among competing commitments with no governing stage belongs
to prioritization; a condition that must hold before work can start belongs to prerequisite; a local
improvement with no system-level effect belongs to product experience or simplification; and a decision
that relief is not worth the cost belongs to stop or defer. Keep the candidate here only when moving
this constraint would change the system rather than make one task feel easier.

## When not to use
Do not use this category when the problem is a single unverified claim, an unclear goal, or a one-off unfinished task. Avoid it when no repeated constraint or system-level effect can be shown. If several commitments compete for attention, use prioritization; if the work should stop because the constraint is not worth relieving, use stop or defer.
