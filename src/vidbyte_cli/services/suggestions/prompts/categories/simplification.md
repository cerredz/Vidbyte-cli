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

## When not to use
Do not use this category when the missing complexity is a true prerequisite, safety control, or user need. Avoid it when the proposed reduction only hides an unresolved decision or shifts burden to another owner. If the main issue is a broad set of competing commitments, use prioritization; if the work no longer earns its cost, use stop or defer.
