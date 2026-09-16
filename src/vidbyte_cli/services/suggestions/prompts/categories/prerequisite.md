# Prerequisite

## Description
A prerequisite identifies a condition that intended work cannot safely or effectively proceed without. It can be evidence, access, capability, authority, preparation, or a prior result. The suggestion makes the dependency explicit instead of allowing it to remain a hidden source of delay. Its usefulness depends on naming the work that becomes possible once the condition exists. A prerequisite is not merely a convenient improvement or a preferred way of working. Use this category when distinguishing a true requirement from a preference changes the next action.

## Why use / use cases
- [ ] **The next task lacks required access or authority.** Work may be ready in every other respect but unable to start legally, technically, or organizationally. Use this category to identify the exact approval, credential, or permission needed.
- [ ] **A decision requires a missing fact or result.** Proceeding without it could invalidate downstream work. Suggest the prerequisite when obtaining the input is necessary rather than merely useful.
- [ ] **A capability must exist before execution.** The caller or team may lack a skill, tool, capacity, or process needed for safe completion. Use it when the capability gap blocks a defined piece of work.
- [ ] **Preparation is required to avoid unsafe progress.** A setup, backup, test environment, or communication may be a condition of proceeding. Recommend it when the risk is tied directly to the intended action.
- [ ] **A dependency is hidden in the current plan.** The work may appear sequentially ready while one external condition remains unstated. Use this category to expose the dependency and its owner.
- [ ] **A preference is being mistaken for a requirement.** The caller may delay useful action for an ideal setup. Suggest clarification of the condition when a safe alternative could allow the main work to continue.
- [ ] **An earlier result gates a later decision.** A measurement, review, prototype, or agreement may determine whether the next phase should begin. Use the category when the gate is explicit and meaningful.
- [ ] **The prerequisite has an alternative path.** A missing condition may be obtainable in more than one way or bypassed with reduced scope. Recommend the category when comparing those paths will prevent unnecessary blockage.

## Things to consider
- What exact condition is necessary for the intended work?
- Which action, phase, or safety boundary does it unlock?
- Is it truly required, or only preferred under the current plan?
- Who can provide, approve, or create the condition?
- What observable evidence shows that it exists and remains valid?
- What is the cheapest safe way to obtain it?
- Can a narrower or alternative route proceed without it?
- What should happen if the condition remains unavailable by the decision point?

## Generation requirements

Every prerequisite suggestion must identify a condition the intended work cannot safely or effectively
proceed without. The proposal should:

- Name the downstream work, outcome, or decision that depends on the condition.
- Explain why the condition is genuinely required rather than merely convenient or preferred.
- Classify the dependency as evidence, access, authority, capability, resource, consent, preparation, or prior result.
- Identify the owner who can provide, approve, or verify the condition and the time it is needed.
- Use supplied context to establish the dependency; label uncertainty about necessity or availability.
- Define the smallest action to obtain, validate, substitute, or escalate the condition.
- State what can proceed safely in parallel and what must remain blocked.
- Define a fallback, deferment, or stop decision if the condition remains unavailable.
- Avoid accumulating a wish list of improvements that do not block the intended work.
- Keep a true blocking condition as the primary mechanism; route research, readiness, ownership, and prioritization to their categories.

## Candidate shape

Shape the candidate as a dependency resolution with a downstream unlock. The reader should know what
cannot proceed, why, who owns the condition, and what happens if it is not obtained.

- In the **summary**, name the intended work, blocking condition, reason it is required, and downstream unlock.
- In the **action sequence**, validate necessity, request or create the condition, confirm it, and release the dependent work.
- In **decision points**, choose whether to wait, substitute, proceed partially, escalate, defer, or stop.
- In **considerations**, cover urgency, authority, access, quality, safety, cost, parallel work, and dependency decay.
- In **dependencies**, name the source, owner, permission, capability, resource, or prior result explicitly.
- In **evidence references**, cite requirements, constraints, failed attempts, or authoritative policy; do not cite preference as necessity.
- In **assumptions**, label why the condition blocks progress and test that assumption where possible.
- In the **completion criterion**, require the condition to be available and verified, or a recorded decision not to proceed.
- If the condition is only useful for a future event, use preparation.

## Valid suggestion directions

Use this category for genuine blockers:

- Obtain access, authority, consent, data, environment, capability, or a required decision.
- Resolve a prerequisite artifact, design, migration, or prior result before dependent work begins.
- Verify that a stated requirement is actually satisfied before relying on it.
- Find a safe substitute when the original dependency is unavailable.
- Assign an owner and deadline to a condition currently treated as ambient responsibility.
- Separate blocked work from parallel work that can proceed without the condition.
- Escalate an unavailable dependency with a clear consequence and decision point.
- Record a deliberate deferment or stop when the condition cannot be obtained in time.
- Reclassify a preference as optional when it does not truly block the outcome.

## Alignment check

The candidate is aligned when the intended work cannot safely or effectively proceed without the named
condition. It must explain the downstream unlock and the response if the condition remains unavailable.
A useful prerequisite narrows the gate; it does not turn every desirable improvement into a blocker.

Reject or reroute candidates that:

- Prepare for a future trigger rather than block current work; use preparation.
- Gather evidence about an unknown necessity; use investigation or verification.
- Resolve unclear ownership or sequence among actors; use coordination.
- Rank several valid commitments; use prioritization.
- Describe a quality preference that can be deferred without changing safety or outcome.

The primary decision must be whether this condition is truly required before the intended work can proceed.

## When not to use
Do not use this category for information that would be interesting but cannot block the intended action. Avoid it when the condition is already available or when the real issue is a queue, owner, or decision rather than a requirement. If readiness is for a future event, use preparation; if the caller needs to find out whether a claim is true, use investigation or verification.
