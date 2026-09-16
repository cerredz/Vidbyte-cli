# Leverage

## Description
A leverage suggestion creates one asset or improvement that benefits several credible future efforts. Its value comes from reuse, from reduced coordination, from accumulated knowledge, or from a recurring cost that stops recurring. What makes it credible is named downstream consumers with near-term needs, not an argument from scale that nobody has checked. The pattern being generalized has to be visible in work that has already happened, because a shared abstraction built before the shared pattern appears will encode the wrong seam and cost more than it saves. Maintenance, ownership, documentation, and adoption are part of the investment rather than free consequences of building it. An asset with no owner decays into an obstacle that everyone routes around.

The suggestion should name the smallest reusable form that solves the observed repetition, since the temptation in this category is to build the general case rather than the shared one. It should say who owns maintenance, access, and eventual retirement, because assets that cannot be retired accumulate indefinitely. It should account for adoption and migration effort, which regularly exceeds construction effort and is the most common reason a good shared asset produces no benefit. It should say how reuse and payback will be observed over time, so that the investment can be judged rather than assumed. It should state the evidence that the pattern is stable, because generalizing an unstable pattern locks in a shape that the next requirement will break. Where the consumers cannot be named, what is being proposed is speculation with a build cost.

## Why use
Use this category when the same work keeps being done and the repetition is visible in the record rather than in an intuition. Repeated effort is a tax that nobody notices individually, because each instance is small and each is justified on its own terms. Aggregating it is the insight, and once aggregated the case for a shared asset is usually obvious and was previously invisible. That aggregation is something a suggestion agent can do and a person inside the work usually cannot.

The category also carries an unusual discipline: it argues for *delaying* generalization until the pattern is real. Most advice about reuse is enthusiastic about it, which is why so much premature abstraction exists. The honest position is that reuse has a cost curve — build, maintain, document, migrate — and that the curve is only favourable when the consumers are real and the shape is stable. Insisting on named consumers and observed repetition is what keeps this category from becoming a licence to build infrastructure nobody asked for.

Distinguish it from its neighbours. Simplification removes complexity from the current result and may reduce reuse rather than create it, so the two can point in opposite directions. Long-term directions builds capability for a future that is not yet specified, whereas leverage requires specific near-term consumers. Preparation builds readiness for one anticipated event rather than for many recurring ones. Delegation moves work to another owner without making it cheaper to do. Use leverage when one bounded effort demonstrably improves more than one future task, and someone will own the result.

## Use cases
- **The same work is being repeated.** Research, setup, explanation, or transformation may recur across tasks. Build the shared asset when the pattern is stable enough that reuse exceeds maintenance.
- **Several future users need the same evidence.** A durable record, dataset, decision log, or reference may prevent duplicate discovery. Use it when the consumers and the access path are both credible.
- **A common interface would reduce coordination.** A template, contract, convention, or reusable workflow may ease future handoffs. Use it when the interface solves a repeated boundary problem rather than adding ceremony.
- **An early artifact can become a building block.** Current work may yield a component, example, or capability that later tasks extend. Preserve the seam now when reconstructing it later would cost more.
- **Learning can compound across tasks.** A documented principle, measurement, or postmortem may improve several future decisions. Use it when the lesson is specific enough to apply and verify elsewhere.
- **A small investment removes a recurring cost.** Automation, indexing, standardization, or precomputation may repay over many uses. Check that the frequency and count actually support it.
- **Consistency matters and varies.** Shared checks, examples, or defaults may reduce variation across related work. Use it when a clear owner will maintain them.
- **The current change creates a reusable capability.** A new permission, integration, measurement, or process may serve more than its original purpose. Recommend it when the additional consumers have specific near-term needs.
- **Onboarding keeps costing the same conversation.** The same explanation repeated to each new participant is a durable, measurable cost. Capture it once, and say who keeps it current.
- **A scarce expert is the only route to a routine answer.** One person may be repeatedly consulted for something that could be written down. Externalize the knowledge rather than scaling the person.
- **Several teams are independently solving one problem.** Parallel effort on the same need is repetition across space rather than time. Consolidate when the requirements genuinely coincide.
- **A manual step precedes every instance of the work.** Setup, cleanup, or conversion may be paid on every run. Remove it once when the run count justifies the build.

## When not to use
- **The task is a one-off.** Reuse cannot repay an investment that is never reused.
- **The consumers cannot be named.** A hypothetical audience is not evidence of demand.
- **The pattern is still moving.** Generalizing an unstable shape locks in the wrong seam.
- **Generalization would slow the current work.** Paying the abstraction cost before the second use is usually a loss.
- **Nobody will own the asset.** An unmaintained shared asset becomes an obstacle rather than a benefit.
- **Adoption cost exceeds the saving.** An asset nobody migrates to delivers none of its promised return.

Route the suggestion elsewhere when one of those signals holds. Removing complexity from the current result belongs to simplification, and readiness for one anticipated event belongs to preparation. A capability worth developing over an extended horizon without named near-term consumers belongs to long-term directions, and moving work to a better-placed owner belongs to delegation. If the repetition is really a limiting point in the flow, use bottleneck, and if the pattern is not yet understood well enough to generalize, use investigation first.
