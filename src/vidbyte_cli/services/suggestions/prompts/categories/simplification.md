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

Every simplification suggestion must remove avoidable scope, components, coordination, or cognitive load
while protecting the essential result. The category exists because complexity accumulates by default:
every addition was justified at the time, nothing removes itself, and the total cost is paid by everyone
who has to understand, maintain, or work around the result afterwards. A simplification is therefore
specific about what goes — naming the machinery being removed, not praising simplicity as a value — and
equally specific about what must survive, since the line between optional and load-bearing is exactly
what the proposal is asserting. Removal is not free either. It creates new limitations, closes options,
and sometimes moves work onto a different owner, and a proposal that does not name that tradeoff is
hiding half the decision. Because the line can be drawn wrongly, the safer shape is reversible or staged,
with a seam where complexity could return if it turns out to have been needed. The proposal should:

- Name what is essential, what is optional, and what complexity is being removed.
- Explain whose effort, confusion, maintenance, or coordination is reduced and how the benefit appears.
- Preserve safety, accessibility, quality, compliance, and downstream contracts that users or owners
  rely on.
- Identify the new limitation, edge case, or burden the reduction may create.
- Prefer a reversible deletion, smaller boundary, or staged reduction before removing a true dependency.
- Define how the simplified result will be tested and who must accept the tradeoff.
- Avoid hiding an unresolved decision, shifting work to another owner, or calling missing capability
  simplicity.
- State the expansion seam or condition that would justify restoring complexity later.
- Confirm that the removed part has no consumer who quietly depends on it.

## Alignment check

Alignment, for simplification, means the candidate takes something away and the result is still worth
having. Scope, components, steps, coordination, or things a person has to hold in mind have accumulated
around an outcome, and the candidate identifies which of them are not carrying their weight. An aligned
candidate names the specific thing being removed, says whose effort or confusion drops as a result, and
asserts clearly which part is essential and must survive. Advocating simplicity in general is not a
suggestion; the substance is the cut.

The second half of alignment is honesty about the cost of cutting. Removal closes options, creates edge
cases, and can push work onto someone else, so an aligned candidate states the limitation it accepts and
who has to agree to it, and prefers a reversible or staged reduction where the essential line is
uncertain. Calling something unfinished or unsafe "simple" is a misdescription rather than a
simplification. Removing a required condition or a safety control belongs to prerequisite or risk
prevention; ending work because its value no longer justifies its cost belongs to stop or defer; choosing
among competing commitments belongs to prioritization; and adding a capability while claiming to reduce
scope belongs nowhere. Keep the candidate here only when the live question is what can be removed while
keeping the result worth having.

## When not to use
Do not use this category when the missing complexity is a true prerequisite, safety control, or user need. Avoid it when the proposed reduction only hides an unresolved decision or shifts burden to another owner. If the main issue is a broad set of competing commitments, use prioritization; if the work no longer earns its cost, use stop or defer.
