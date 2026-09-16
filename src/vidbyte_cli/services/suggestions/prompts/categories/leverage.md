# Leverage

## Description
A leverage suggestion creates one asset or improvement that benefits several credible future efforts. Its value comes from reuse, reduced coordination, accumulated knowledge, or avoided repeated cost. The suggestion should identify real downstream consumers rather than hypothetical scale. It should delay generalization until a shared pattern is visible in the work. Maintenance, ownership, and adoption are part of the investment rather than free consequences. Use this category when one bounded effort can meaningfully improve more than one future decision or task.

## Why use / use cases
- [ ] **The same work is being repeated.** Repeated research, setup, explanation, or transformation may be a candidate for a shared asset. Use this category when the pattern is stable enough that reuse will exceed maintenance cost.
- [ ] **Several future users need the same evidence.** A durable record, dataset, decision log, or reference may prevent duplicate discovery. Suggest leverage when the consumers and access path are credible.
- [ ] **A common interface could reduce coordination.** A template, contract, convention, or reusable workflow may make future handoffs easier. Use it when the interface solves a repeated boundary problem rather than adding ceremony.
- [ ] **An early artifact can become a building block.** Current work may produce a component, example, or capability that future tasks can extend. Recommend it when preserving the right seam is cheaper now than reconstructing it later.
- [ ] **Learning can compound across tasks.** A documented principle, measurement, or postmortem may improve several future decisions. Use the category when the lesson is specific enough to apply and verify elsewhere.
- [ ] **A small investment removes a recurring cost.** Automation, indexing, standardization, or precomputation may pay back over multiple uses. Suggest leverage when the number and frequency of uses support the investment.
- [ ] **A shared asset can make quality more consistent.** Common checks, examples, or defaults may reduce variation across related work. Use it when consistency matters and the asset will be maintained by a clear owner.
- [ ] **The current change creates a reusable capability.** A new permission, integration, measurement, or process may support more than its original use. Recommend leverage when the additional consumers have specific near-term needs.

## Things to consider
- What repeated pattern or cost is visible in actual work?
- Which two or more credible future consumers would reuse the asset?
- What shared mechanism, interface, record, or capability would help them?
- What evidence shows the pattern is stable enough to generalize?
- What is the smallest reusable form that avoids premature abstraction?
- Who owns maintenance, documentation, access, and retirement?
- What adoption or migration effort could erase the expected benefit?
- How will reuse and payback be observed over time?

## Generation requirements

Every leverage suggestion must create one bounded asset, improvement, relationship, or decision that
benefits several credible future efforts. The category exists because repeated cost is invisible when
paid one instance at a time: the same lookup, the same setup, the same negotiation, absorbed again and
again until someone notices the pattern. Leverage pays that cost once. The requirement that keeps it
honest is real consumers — at least two identifiable future uses, not a hypothetical audience — because
an abstraction built for imagined reuse is pure overhead. Timing matters just as much: generalizing
before the shared pattern is visible produces the wrong abstraction, and the wrong abstraction is harder
to remove than the duplication it replaced. Reuse is also not free. Ownership, maintenance, adoption,
and the cost of changing the asset later are part of the investment, and a proposal that omits them is
understating the price. The proposal should:

- Name at least two realistic downstream consumers or uses rather than relying on hypothetical scale.
- Explain the shared mechanism that makes reuse valuable and why one investment serves those consumers.
- Delay abstraction until a repeated pattern, common interface, or durable need is visible.
- Include ownership, maintenance, adoption, and update cost rather than treating reuse as free.
- Preserve the current outcome while making future work faster, clearer, safer, or less coordinated.
- Define the smallest reusable asset that can test whether the pattern is actually shared.
- Avoid generalizing unstable details or creating a platform before use cases justify it.
- Measure adoption, reuse, avoided effort, quality, or coordination rather than counting artifacts.
- Say when to stop generalizing if adoption or the shared pattern fails to appear.

## Alignment check

Alignment, for leverage, means the candidate spends once to make several later efforts cheaper. The
caller is paying a repeated cost — rebuilding the same setup, re-answering the same question,
re-negotiating the same agreement — and one bounded investment could remove it from all of them. An
aligned candidate names the consumers who would actually benefit, explains the shared mechanism that
makes one asset serve them, and keeps the asset small enough to test whether the pattern is real.
Generality with no adopter is not leverage; it is an abstraction the caller now has to maintain.

The second half of alignment is total cost. An asset has an owner, a maintenance burden, an adoption
curve, and a future in which it must change, so an aligned candidate counts those against the benefit
and says when to stop generalizing if the shared pattern never materializes. Removing complexity from
one current result belongs to simplification, because its value is local. A broad capability or market
to develop over years belongs to long-term directions. Finishing a one-off obligation belongs to
completion, and building an abstraction before any shared pattern or consumer exists belongs nowhere at
all. Keep the candidate here only when the live question is whether a reusable asset earns its cost
across real future work.

## When not to use
Do not use this category for a one-off task, a hypothetical audience, or an abstraction whose consumers cannot be named. Avoid it when generalization would slow the current work or lock in an unstable pattern. If the goal is to remove complexity from the current result, use simplification; if the asset supports a broader future capability rather than repeated near-term use, use long-term directions.
