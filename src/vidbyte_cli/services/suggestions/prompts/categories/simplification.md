# Simplification

## Description
A simplification removes avoidable scope, components, coordination, or cognitive load while protecting the result that matters. It is a subtractive suggestion, and subtraction has to be specific: what is removed must be named, because praising simplicity in the abstract commits nobody to anything and changes nothing. The central judgment is separating optional machinery from the parts that downstream users, operators, or decisions actually depend on. That separation is not obvious from inside the work, where every piece has a remembered reason and the reasons are no longer all valid. Complexity accumulates one defensible decision at a time, which is why it is rarely removed by the same process that created it. A simplification is the deliberate counter-move.

The suggestion must also state what the reduction costs, since every removal creates a new limitation, risk, or foreclosed option. Claiming a simplification is free is the fastest way to have it reversed by the first person who needed the removed capability. It should name the evidence that the current complexity is producing cost or confusion, rather than asserting that fewer things are better. It should identify who could be harmed by the removal and whether the burden is being genuinely eliminated or merely shifted to another owner, because shifted burden is the most common counterfeit in this category. It should say whether the reduction is reversible without losing important state. It should say how the simpler result will be verified against the original acceptance condition, and which expansion seam remains available without being built now.

## Why use
Use this category when accumulated complexity has become the thing limiting the work rather than a side effect of it. This happens on a predictable schedule, because complexity is added incrementally by people solving real problems and removed by nobody in particular. The cost shows up diffusely — slower changes, more coordination, more places to be wrong, a longer explanation for every newcomer — and diffuse costs do not generate their own repair. Naming the specific removable piece is what converts a general feeling of heaviness into an action.

The category also earns its place by countering a specific bias in suggestion-making. Almost every other category proposes adding something: a step, a check, an asset, a test, a direction. Over time an advisor that only adds becomes a source of burden regardless of the quality of each individual suggestion. Having a category whose move is removal keeps the total load in view, and it makes it possible to recommend subtraction as a first-class action instead of an apology.

Distinguish it from its neighbours. Stop or defer abandons work entirely, where simplification keeps the outcome and reduces the means. Completion closes a remaining obligation rather than removing an existing one. Leverage often argues in the opposite direction, towards shared machinery, and the two should be weighed against each other rather than applied in sequence. Bottleneck relieves a constraint on flow, which complexity can cause but does not exhaust. Use simplification when the essential result survives intact and the effort or clarity saved exceeds what is given up.

## Use cases
- **Optional scope has accumulated.** Extra features, formats, audiences, or edge cases may dilute the essential result. Remove a named portion without weakening the commitment that matters.
- **A workflow has too many steps or handoffs.** Repeated coordination may add delay without adding quality or control. Shorten the path while preserving the necessary decision and acceptance points.
- **A component costs more than it returns.** A tool, abstraction, integration, or configuration may have become a liability. Remove or replace it with a simpler mechanism.
- **Users or operators must hold too much context.** Complex choices, labels, or exceptions may produce errors and hesitation. Use a clearer default or a smaller choice set while preserving real control.
- **Generality arrived before the pattern.** Flexibility may have been built before a stable shape existed. Narrow the solution and leave a deliberate expansion seam.
- **A requirement has been confused with its implementation.** The current machinery may be one route to the outcome rather than the outcome. Propose a simpler route that meets the same acceptance condition.
- **Fewer parts would improve reliability.** Reducing moving parts, states, or dependencies may lower failure probability. Use it when the gain is checkable and the removed capability is understood.
- **The result must be explainable.** Complexity may be preventing adoption or review. Reduce the concepts when that makes the important behaviour inspectable.
- **Two mechanisms do the same job.** Parallel paths that overlap force everyone to know both. Consolidate, and say which one survives.
- **Configuration has replaced decisions.** Options may exist because nobody wanted to choose. Pick a default, and remove the choice that nobody exercises.
- **Dead paths remain in place.** Code, process, or documentation may serve a case that no longer exists. Remove it once the case is confirmed gone.
- **Onboarding is the symptom.** A long explanation for newcomers is a reliable measure of accumulated complexity. Target what takes longest to explain.

## When not to use
- **The complexity is a true prerequisite.** Removing a required condition creates a failure, not a simplification.
- **The removed part is a safety control.** Guards look like overhead precisely when they are working.
- **A real user need depends on it.** A capability with users is not optional because it is inconvenient.
- **The reduction hides an unresolved decision.** Deferring a choice by deleting its surface does not resolve it.
- **The burden is shifted rather than removed.** Moving work to another owner is a transfer wearing a saving's clothes.
- **The work no longer earns its cost at all.** Making unwanted work simpler still produces unwanted work.

Route the suggestion elsewhere when one of those signals holds. Work that should end belongs to stop or defer, and a required condition belongs to prerequisite. A protective control belongs to risk prevention, and a real user need belongs to product and experience. Competing commitments belong to prioritization, and a shared asset that would remove repeated cost belongs to leverage. If the complexity is the limiter on flow rather than on comprehension, use bottleneck so the intervention targets the constraint.
