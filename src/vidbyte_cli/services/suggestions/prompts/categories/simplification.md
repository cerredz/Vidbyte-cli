# Simplification

## Description
A simplification removes avoidable scope, components, coordination, or cognitive load. It protects the essential result while making the path easier to complete, understand, and maintain. The suggestion should name what is removed instead of praising simplicity in the abstract. It should distinguish optional machinery from a requirement that downstream users or decisions rely on. A good simplification also notices what new limitation, risk, or lost option the reduction creates. Use this category when the saved effort or clarity exceeds the value of what is discarded.

## Why use / use cases
- [ ] **The work has accumulated optional scope.** Extra features, formats, audiences, or edge cases may dilute the essential result. Use this category to remove a named portion without weakening the commitment that matters.
- [ ] **A workflow has too many steps or handoffs.** Repeated coordination may create delay without adding quality or control. Suggest simplification when a shorter path preserves the necessary decision and acceptance points.
- [ ] **A component adds more maintenance than value.** A tool, abstraction, integration, or configuration may have become a liability. Use it when the component can be removed or replaced with a simpler mechanism.
- [ ] **Users or operators must hold too much mental context.** Complex choices, labels, or exceptions may cause errors or hesitation. Recommend the category when a clearer default or reduced choice set preserves user control.
- [ ] **A general solution is premature.** The caller may be building flexibility before a stable pattern exists. Use simplification to narrow the current solution and leave an intentional expansion seam.
- [ ] **A requirement is being confused with its implementation.** The current machinery may be one way to achieve the outcome, not the outcome itself. Suggest a simpler route when it maintains the actual acceptance condition.
- [ ] **A small reduction can improve reliability.** Fewer moving parts, states, or dependencies may lower failure probability. Use it when the reliability gain can be checked and the removed capability is understood.
- [ ] **The result needs to be explainable to its users or owners.** Complexity may prevent effective adoption or review. Recommend simplification when reducing concepts makes the important behavior easier to inspect.

## Things to consider
- What essential outcome, behavior, or guarantee must remain?
- Which scope, component, step, dependency, or choice is actually optional?
- What evidence shows the current complexity creates cost or confusion?
- What user, operator, or downstream need could be harmed by removal?
- What new limitation, risk, or lost flexibility will the simpler form create?
- Can the reduction be reversed without losing important state?
- How will the simpler result be verified against the original acceptance condition?
- What expansion seam should remain possible without building it now?

## Generation requirements

Every simplification suggestion must remove avoidable scope, components, coordination, or cognitive
load while protecting the essential result. The proposal should:

- Name what is essential, what is optional, and what complexity is being removed.
- Explain whose effort, confusion, maintenance, or coordination is reduced and how the benefit appears.
- Preserve safety, accessibility, quality, compliance, and downstream contracts that users or owners rely on.
- Identify the new limitation, edge case, or burden the reduction may create.
- Use supplied evidence about friction, failure, maintenance, or unused capability; label assumptions.
- Prefer a reversible deletion, smaller boundary, or staged reduction before removing a true dependency.
- Define how the simplified result will be tested and who must accept the tradeoff.
- Avoid hiding an unresolved decision, shifting work to another owner, or calling missing capability simplicity.
- State the expansion seam or condition that would justify restoring complexity later.
- Keep removal of avoidable complexity as the primary mechanism; route priority, stopping, and prerequisites to focused categories.

## Candidate shape

Shape the candidate as a deliberate reduction with a protected essential outcome. The reader should know
what disappears, what remains, who benefits, and how the new limitation is accepted.

- In the **summary**, name the essential result, complexity being removed, and expected saved effort or clarity.
- In the **action sequence**, inventory components or steps, remove the smallest avoidable part, test the result, and record the tradeoff.
- In **decision points**, choose scope, deletion boundary, compatibility, migration, quality floor, and restoration trigger.
- In **considerations**, cover user burden, owner burden, safety, accessibility, maintenance, downstream contracts, and lost capability.
- In **dependencies**, name consumers, requirements, approvals, data, or interfaces that constrain removal.
- In **evidence references**, cite observed friction, unused paths, repeated errors, or maintenance cost; do not cite aesthetic preference as complexity.
- In **assumptions**, label what can be removed safely and how affected users will reveal a missed need.
- In the **completion criterion**, require a smaller result that preserves the essential outcome and records the accepted limitation.
- If the removed piece is a true prerequisite or safety control, do not simplify it.

## Valid suggestion directions

Use this category for honest reductions:

- Remove optional scope that does not change the essential outcome.
- Collapse repeated steps, interfaces, approvals, or coordination where the risk is low.
- Reduce choices, configuration, or cognitive load at the moment users need to act.
- Replace a complex component with a simpler mechanism and state the lost capability.
- Delay generalization, automation, or abstraction until repeated demand exists.
- Narrow supported inputs, audiences, or workflows to a reliable boundary.
- Delete unused documentation, paths, or compatibility burden with evidence.
- Simplify a handoff or decision record without hiding necessary context.
- Preserve a seam for future expansion without building it now.

## Alignment check

The candidate is aligned when removing a named source of avoidable complexity preserves the essential
result and makes effort, clarity, or maintenance better. It must state what is discarded and what new
limitation is accepted. Calling an unfinished or unsafe solution “simple” is not simplification.

Reject or reroute candidates that:

- Remove a required condition or safety control; use prerequisite or risk prevention instead.
- End work because its value no longer justifies cost; use stop or defer.
- Choose among competing commitments; use prioritization.
- Add a new capability while claiming to reduce scope.
- Shift effort or confusion to another owner without recognizing the tradeoff.

The primary decision must be what can be removed while keeping the result worth having.

## When not to use
Do not use this category when the missing complexity is a true prerequisite, safety control, or user need. Avoid it when the proposed reduction only hides an unresolved decision or shifts burden to another owner. If the main issue is a broad set of competing commitments, use prioritization; if the work no longer earns its cost, use stop or defer.
