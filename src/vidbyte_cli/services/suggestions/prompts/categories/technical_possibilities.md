# Technical Possibilities

## Description
A technical-possibilities suggestion explores what technology could make materially better or possible. It stays at the level of capability and user or system value rather than prescribing implementation details prematurely. The possibility should connect to a real constraint, opportunity, or desired outcome in the caller’s context. It should identify what new behavior, scale, speed, or reliability the capability would enable. Technical novelty is not valuable when it adds complexity without changing the result or decision. Use this category when a focused feasibility question can separate a promising capability from an attractive fantasy.

## Why use / use cases
- [ ] **A current constraint may be technically changeable.** Limited speed, scale, access, accuracy, or reliability may not be permanent. Use this category when a capability could alter the constraint and the value of that change is clear.
- [ ] **A new system behavior could unlock an outcome.** Automation, integration, computation, or sensing may enable something the current process cannot. Suggest technical possibilities when the behavior matters more than the technology label.
- [ ] **A manual process is limiting useful scale.** Repetition may consume capacity or introduce inconsistency. Use it when a technical capability could improve the relevant outcome without shifting hidden work elsewhere.
- [ ] **A platform or tool exposes a relevant capability.** Existing infrastructure may make a new path unusually feasible. Recommend this category when the capability can be mapped to a specific user, system, or business need.
- [ ] **A technical choice could improve resilience.** Redundancy, observability, isolation, or graceful degradation may reduce material exposure. Use it when the reliability benefit is connected to a defined failure or service expectation.
- [ ] **A prototype can answer feasibility cheaply.** The caller may need to know whether latency, integration, data quality, or control is achievable. Suggest a small technical spike when its result will change the broader decision.
- [ ] **A capability could reduce user or operator burden.** Better interfaces, defaults, or assistance may be technically enabled. Use this category when the burden and improved behavior are identified rather than assuming any automation is valuable.
- [ ] **A technical possibility deserves comparison with non-technical routes.** The capability may compete with process, staffing, or scope changes. Recommend it when the technical route has a distinct advantage worth testing.

## Things to consider
- What user, system, or organizational outcome would the capability improve?
- Which current constraint or opportunity makes it relevant now?
- What new behavior, scale, speed, quality, or resilience would become possible?
- What feasibility question is most decision-critical?
- What data, integration, dependency, or operational burden would it introduce?
- Which people or systems would own and maintain the capability?
- What smallest prototype or measurement can test feasibility?
- What result would make the technical possibility less valuable than a simpler route?

## Generation requirements

Every technical-possibilities suggestion must explore a capability technology could make materially
better or newly possible, tied to a user, system, or business outcome. The category exists because
feasibility moves: things that were impossible, too slow, too expensive, or too unreliable become
ordinary, and the caller's mental model of what is achievable is usually older than the tools available.
The requirement that keeps this grounded is the outcome anchor — the proposal has to name what behavior,
scale, speed, reliability, cost, or access changes, because a capability with no consequence is trivia.
It also has to stay at the level of capability rather than descending into implementation, since
committing to a specific technology before the value is established locks in a choice that has not been
earned. New capability brings new cost: maintenance, observability, privacy, security, accessibility, and
someone to operate it. And because attractive capabilities are often worse than the boring alternative,
the proposal needs a bounded check and a comparison against the simpler route. The proposal should:

- Name the real constraint or opportunity and the behavior or result a technical capability would enable.
- Stay at capability and value level before prescribing implementation details or specific technology.
- Explain why technology changes feasibility, quality, speed, scale, cost, or access in this context.
- Identify affected users, operators, systems, dependencies, and new complexity or failure modes.
- Propose a bounded feasibility, usability, safety, or integration check before broad investment.
- Account for maintenance, observability, privacy, security, accessibility, and operational ownership.
- Define what evidence would make the possibility more or less valuable than a simpler route.
- Avoid novelty as a substitute for outcome and avoid implementation detail unsupported by the problem.
- Compare the capability against the simplest approach that would produce the same outcome.

## Alignment check

Alignment, for technical possibilities, means technology is the thing that changes what is achievable.
Some constraint the caller has been designing around — a limit on speed, scale, cost, reliability, or
access — may no longer hold, and the candidate asks what becomes possible if it does not. An aligned
candidate names that constraint, states the capability, and says what new behavior or result follows for
a user, a system, or the business. The outcome anchor is what separates this from enthusiasm: a
capability with no consequence for anyone is interesting rather than useful, and architecture or
implementation detail with no outcome behind it is not a possibility, it is a preference.

The second half of alignment is keeping feasibility honest. A promising capability can still be the
wrong answer once maintenance, security, privacy, accessibility, and operational ownership are counted,
so an aligned candidate proposes a bounded feasibility or integration check and says what evidence would
make the simpler route preferable. Improving a known interaction with no distinct capability question
belongs to product and experience; confirming that an existing capability works as claimed belongs to
verification; choosing a broad organizational direction belongs to strategy; and starting implementation
with no user, system, or business outcome belongs nowhere. Keep the candidate here only when the live
question is whether this technical possibility changes what can be done enough to justify its cost and
risk.

## When not to use
Do not use this category for implementation details that are not tied to a meaningful outcome or for technology chosen because it is novel. Avoid it when the user or system need is unclear, or when a known capability merely needs execution. If the main concern is how people experience the result, use product and experience; if the question is whether the capability is already working as claimed, use verification.
