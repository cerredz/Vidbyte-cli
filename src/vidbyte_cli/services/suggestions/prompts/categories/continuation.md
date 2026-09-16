# Continuation

## Description
A continuation suggestion advances an accepted plan from its current state to the next bounded step. It assumes the direction and desired outcome are already sufficiently clear. The suggestion should preserve the plan’s existing commitments while identifying what can happen next. It should be concrete enough to start and narrow enough to stop or reassess. A continuation is not a new strategy disguised as execution or a request to repeat work without learning. Use this category when momentum is valuable and no unresolved prerequisite or decision should interrupt the path.

## Why use / use cases
- [ ] **The plan has been accepted but paused.** The direction is settled and the current state is known. Use this category to identify the next action that restores movement without reopening the plan.
- [ ] **One milestone has just been reached.** A completed step may make the next dependency or action visible. Suggest continuation when the new state supports a bounded follow-on rather than a fresh planning cycle.
- [ ] **The next step is obvious but unowned.** Work can stall even when no strategic question remains. Use it to name the action, owner, input, and completion signal that carry the plan forward.
- [ ] **A sequence has a natural next operation.** The current stage may produce an artifact or result consumed by the following stage. Recommend this category when the dependency is explicit and the handoff is ready.
- [ ] **Momentum reduces avoidable restart cost.** Pausing too long may require reloading context, rebuilding setup, or losing stakeholder attention. Use it when starting the next bounded step now has a credible continuity benefit.
- [ ] **The next action can produce useful progress independently.** A plan may continue while a later decision remains outside the immediate step. Suggest it when the action does not create irreversible commitment ahead of that decision.
- [ ] **An accepted task needs decomposition into the next move.** The overall plan may be clear while the immediate action is still too broad to begin. Use continuation to reduce it to one executable slice with a stopping condition.
- [ ] **The current result calls for a predictable follow-up.** A review, measurement, deployment, or communication may be part of the agreed path. Recommend it when the follow-up is a plan obligation, not a new idea.

## Things to consider
- What plan, decision, or commitment has already been accepted?
- What changed in the current state since the previous step?
- Which single action is next in the existing sequence?
- What input, owner, and output make that action startable?
- What bounded result marks the step complete?
- Does the step preserve the plan’s direction and scope?
- Could executing it create an irreversible commitment too early?
- What condition would trigger reassessment instead of another continuation?

## Generation requirements

Every continuation suggestion must advance a plan the caller has already accepted without reopening its
direction. The category exists to protect momentum: when a route has been settled, the expensive failure
is not moving too slowly but returning to the decision that was already made and paying for it again.
A continuation therefore inherits the plan's outcome, scope, audience, quality bar, and constraints
rather than restating or renegotiating them, and its job is to name the next movement that follows from
what is already done. The step must be bounded on both ends — concrete enough to begin without another
planning pass, and small enough that the caller can reassess afterwards instead of committing blindly to
the remainder. Continuation is also where new direction most easily hides, because a step framed as
routine can carry scope, opportunity, or an unsettled tradeoff inside it, and the proposal has to keep
that boundary honest. The proposal should:

- Name the accepted outcome, the current state, and the next movement that follows from completed work.
- Reuse available information, artifacts, and permissions instead of inventing a new rationale.
- Keep the scope, audience, quality bar, and constraints of the accepted plan intact.
- Identify the concrete action that reduces delay between the current step and the next useful result.
- State the decision or observation that would justify continuing, changing course, or stopping.
- Avoid hiding a new strategy, opportunity, or unresolved goal inside a supposedly routine next step.
- Define dependencies and ownership so the next action can begin without another abstract planning pass.
- Make progress observable through an artifact, state change, handoff, or decision.
- Stop at a point where reassessment is still cheap rather than at the end of the remaining plan.

## Alignment check

Alignment, for continuation, means the candidate moves accepted work forward from where it actually
stands. The direction is settled and the caller has momentum; what they need is the next bounded step,
grounded in the current state rather than in the plan as originally imagined. An aligned candidate reads
what is done, what is in progress, and what is blocked, and then names one movement that can start now
and produce something inspectable. It may surface a condition that would justify reassessing later, but
it does not ask the caller to re-decide the route before acting.

The second half of alignment is refusing to smuggle. A step that quietly introduces new scope, a new
audience, a new opportunity, or an unresolved tradeoff is a direction change wearing the clothes of
execution, and it costs the caller the momentum this category exists to protect. Closing the last
remaining obligation is completion; settling a disputed goal, route, or tradeoff is goal clarification,
alternative, or strategy; a missing condition that blocks safe progress is prerequisite or
investigation; optional nearby value is adjacent opportunity; and concluding that the work is no longer
worth advancing is stop or defer. Keep the candidate here only when the live question is what accepted
work can move forward from the current state now.

## When not to use
Do not use this category when the direction is still disputed, the goal is unclear, or a required condition is missing. Avoid it when the proposed step is actually a new opportunity, alternative, or strategy. If the current plan has reached its final obligation, use completion; if continuing is no longer worthwhile, use stop or defer.
