# Risk Prevention

## Description
A risk-prevention suggestion reduces the likelihood or the impact of a plausible failure. It joins a recognizable exposure to a guard, a signal, or a recovery plan that is proportionate to what the failure would cost. Proportionality is the whole discipline here, because every control has an ongoing burden and a set of controls assembled without regard to cost becomes its own failure mode. The suggestion should address risks capable of changing the outcome rather than every concern that can be imagined, and the difference between those two sets is large. Prevention is strongest when the protection is in place before the exposure begins, since a guard added afterwards protects only the remainder. Where prevention cannot be complete or would cost too much, detection and recovery are the honest substitutes.

The suggestion should describe the failure mode concretely enough to be argued with — how it happens, what it damages, how visible it would be, how reversible. It should identify the prevention point that occurs before the exposure or the commitment, because that point is usually earlier than instinct suggests and is frequently already past. It should say how the control avoids creating a burden equal to or greater than the risk, which is the most common way well-intentioned safeguards are quietly abandoned. It should name the signal that would detect the failure early enough to matter, since detection after compounding is not detection. It should name the fallback that preserves the core obligation when the primary route fails. It should also name who owns the control, monitors it, and revises it when conditions change, because an unowned control decays into a false assurance.

## Why use
Use this category when a specific failure is plausible, consequential, and cheaper to guard against than to repair. That combination is narrower than general caution and much more useful. Most concerns fail one of the three tests: they are imaginable but not plausible, plausible but not consequential, or consequential but no cheaper to prevent than to fix. Filtering on all three is what makes a prevention suggestion worth the reader's attention rather than another item on a list of things that could go wrong.

The category also addresses a timing asymmetry that people reliably misjudge. The cost of a guard falls over time until the moment of exposure, after which it rises sharply, and the window in which prevention is cheap closes quietly and without announcement. A suggestion that names the last cheap moment is doing something the caller almost certainly is not doing for themselves, because attention at that stage is fully occupied by making the thing work.

Distinguish it from the categories around it. Verification confirms that a specific claim is true before something is relied on, which is a check rather than a guard, though a verification can serve as one. Preparation builds readiness for an expected event, where prevention addresses a failure that may never occur. Bottleneck relieves a constraint on flow rather than protecting against a failure. Stop or defer removes the exposure entirely by not doing the thing, which is sometimes the correct and unwelcome answer. Use risk prevention when the work should continue and one proportionate control materially improves its odds.

## Use cases
- **A known failure mode could derail the outcome.** There may be enough context to describe exactly how the failure would occur. Add a guard that reduces likelihood or impact before exposure grows.
- **An irreversible action is approaching.** A check, backup, approval, or staged release may preserve recovery before the point of no return. Keep the protection proportionate to the consequence.
- **A handoff can lose critical information.** Ambiguous ownership, missing context, or an unverified interface may produce predictable failure. Add a narrow contract or confirmation at the boundary.
- **A small control prevents expensive rework.** A validation, limit, default, or precondition may catch the problem early. Recommend it when the control costs less than repairing the result.
- **Exposure is growing faster than confidence.** The work may be reaching more users, systems, data, or stakeholders than the evidence supports. Add staged exposure or a leading signal.
- **Detection is slower than the consequence.** An alert, audit, or checkpoint may be needed before the failure compounds. Use it when faster detection creates a credible recovery window.
- **A fallback would preserve the core obligation.** The primary route may fail despite reasonable safeguards. Define a concrete alternate path or recovery state.
- **A recurring incident needs a durable guard.** Repeated warnings or manual fixes suggest prevention belongs in the workflow. Recommend it when the pattern and the control's owner are both clear.
- **A single point of failure has no cover.** One person, credential, dependency, or machine may hold the whole path. Reduce the concentration, or make the failure survivable.
- **A quiet failure mode exists.** Some failures produce no signal until damage is substantial. Add observability specifically where silence is possible.
- **The blast radius is larger than the change.** A small modification may reach far beyond its apparent scope. Contain it before shipping, not after.
- **Assumptions are being carried into a new context.** Controls designed for one scale, region, or population may not hold in another. Re-examine them at the boundary rather than after the incident.

## When not to use
- **The concern is hypothetical.** Imaginable failures with no plausibility consume attention indefinitely.
- **The control burden exceeds the consequence.** Protection more expensive than the loss is a loss chosen deliberately.
- **No one can own or maintain the control.** An unmaintained guard becomes false assurance, which is worse than none.
- **The claim simply needs checking.** Confirming a fact is not the same as guarding against a failure.
- **The goal is unclear.** Protecting an undefined outcome protects nothing in particular.
- **The right answer is to drop the exposure.** Guarding work that should not happen is an expensive way to keep it.

Route the suggestion elsewhere when one of those signals holds. A claim to confirm belongs to verification, and readiness for an expected event belongs to preparation. A limiting constraint belongs to bottleneck, and removing the exposure belongs to stop or defer. An undefined outcome belongs to goal clarification, and an unknown likelihood belongs to investigation or experiment. If the risk comes from complexity that nobody needs, simplification removes the exposure rather than guarding it.
