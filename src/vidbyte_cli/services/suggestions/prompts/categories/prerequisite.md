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
proceed without. The category exists because hidden dependencies are the most expensive kind: work
starts, runs into the missing condition halfway, and the cost is paid in rework and delay rather than in
the cheap acknowledgement that would have prevented it. Making the dependency explicit is the whole
point. The discipline that keeps this useful is the line between required and preferred — almost any
improvement can be described as necessary, and a category that accepts that description becomes a wish
list that blocks everything. A prerequisite must therefore name what becomes possible once the condition
exists, and what genuinely cannot start until then, since work that can proceed in parallel should. It
also needs a route: who supplies the condition, by when, and what the caller does if it never arrives.
The proposal should:

- Name the downstream work, outcome, or decision that depends on the condition.
- Explain why the condition is genuinely required rather than merely convenient or preferred.
- Classify the dependency as evidence, access, authority, capability, resource, consent, preparation, or
  prior result.
- Identify the owner who can provide, approve, or verify the condition and the time it is needed.
- Define the smallest action to obtain, validate, substitute, or escalate the condition.
- State what can proceed safely in parallel and what must remain blocked.
- Define a fallback, deferment, or stop decision if the condition remains unavailable.
- Avoid accumulating a wish list of improvements that do not block the intended work.
- Say how the caller can confirm the condition is actually satisfied rather than assumed.

## Alignment check

Alignment, for prerequisite, means the candidate exposes a gate. Work the caller intends to do cannot
start — or cannot start safely — until some condition exists: an approval, an access, a piece of
evidence, a capability, a prior result, someone's consent. An aligned candidate names that condition,
names what it unblocks, and explains why the dependency is real rather than a preference dressed up as a
requirement. It also identifies who can supply it and what the smallest move is to obtain, validate,
substitute, or escalate it, because a blocker with no owner and no route is a complaint rather than a
suggestion.

The second half of alignment is narrowness. Every desirable improvement can be argued into sounding
necessary, and a category that admits them all stops distinguishing anything: an aligned candidate says
what can safely continue in parallel and keeps the blocked set as small as the truth allows. It also says
what happens if the condition never arrives — a fallback, a deferment, or a decision to stop. Readiness
for a future trigger that does not block current work belongs to preparation; establishing whether the
dependency is even real belongs to investigation or verification; unclear ownership or sequencing among
actors belongs to coordination; and choosing among several valid commitments belongs to prioritization.
Keep the candidate here only when the live question is whether this condition is truly required before
the intended work can proceed.

## When not to use
Do not use this category for information that would be interesting but cannot block the intended action. Avoid it when the condition is already available or when the real issue is a queue, owner, or decision rather than a requirement. If readiness is for a future event, use preparation; if the caller needs to find out whether a claim is true, use investigation or verification.
