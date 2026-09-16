# Technical Possibilities

## Description
A technical-possibilities suggestion explores what technology could make materially better or newly feasible. It operates at the level of capability and the value that capability creates, not at the level of implementation detail, because prescribing the mechanism before the value is established reverses the order in which those should be decided. The possibility must attach to a real constraint, opportunity, or desired outcome in the caller's situation rather than to the general availability of a technique. What the suggestion has to name is the new behaviour, scale, speed, quality, or reliability that becomes available, and why that change matters to someone. Technical novelty that adds complexity without changing a result or a decision is a cost, and an easy one to incur. The category is for separating a promising capability from an attractive fantasy.

The suggestion should name the feasibility question that is most decision-critical, since a capability usually stands or falls on one thing — latency, data quality, integration, accuracy, control, cost — rather than on the whole design. It should propose the smallest prototype or measurement that would answer that question, because feasibility is cheap to test and expensive to assume. It should name the data, integration, dependency, and operational burden the capability would introduce, as these accumulate quietly and are paid by people who were not in the conversation. It should say who would own and maintain the result, which is the commitment that outlasts the enthusiasm. It should compare the technical route against the non-technical alternatives — process, staffing, scope — because those are frequently cheaper and are rarely considered once a technical framing takes hold. It should say what result would make the simpler route better.

## Why use
Use this category when a constraint everyone treats as fixed may not be. Teams build durable habits around limits — this takes a day, that cannot be automated, this must be approximate — and those habits persist long after the underlying limit has moved. Surfacing a capability that changes the limit is high-value precisely because nobody inside the habit is looking for it. The suggestion has to carry the value argument, though, since a capability with no constraint behind it is a technology looking for a problem.

The category also protects a specific decision from being made badly. Technical possibilities are usually evaluated either by enthusiasm or by reflexive caution, and both are poor instruments. Naming one decision-critical feasibility question and a small test to answer it replaces both with evidence, and it does so at a cost low enough that the test can be run before anyone has committed to a position. That is the strongest argument this category makes, and it should appear in most suggestions written under it.

Distinguish it from the categories nearest to it. Product and experience argues from a person at a moment and what they would do differently, where this category argues from what becomes possible at all. Experiment tests an uncertainty to inform a decision, and a feasibility spike is a species of experiment, so the distinction is that here the uncertainty is specifically about technical capability. Verification checks whether a claimed capability already works as stated, which is a different question from whether it could. Leverage builds a reusable asset, which a new capability may become but is not by default. Use technical possibilities when the relevant question is what technology makes newly achievable and whether that is worth having.

## Use cases
- **A current constraint may be technically changeable.** Speed, scale, access, accuracy, or reliability limits may not be permanent. Use it when a capability could move the constraint and the value of moving it is clear.
- **A new system behaviour would unlock an outcome.** Automation, integration, computation, or sensing may enable what the current process cannot. Argue from the behaviour rather than the technology's name.
- **A manual process is limiting scale.** Repetition may be consuming capacity or introducing inconsistency. Use it when the capability improves the outcome without relocating the work invisibly.
- **A platform already exposes the capability.** Existing infrastructure may make a new path unusually cheap. Map it to a specific user, system, or business need.
- **A technical choice could improve resilience.** Redundancy, observability, isolation, or graceful degradation may reduce real exposure. Tie the benefit to a defined failure or service expectation.
- **A prototype would settle feasibility cheaply.** The open question may be whether latency, integration, data quality, or control is achievable. Use a small spike when its result changes the broader decision.
- **A capability could reduce operator burden.** Better interfaces, defaults, or assistance may be technically enabled. Identify the burden and the improved behaviour rather than assuming automation helps.
- **The technical route should be compared with non-technical ones.** Process, staffing, or scope changes may compete directly. Recommend it when the technical route has a distinct advantage worth testing.
- **An assumption about cost has aged.** Compute, storage, bandwidth, or model capability may have changed the economics of a rejected idea. Re-examine the decision rather than the technology.
- **Data that exists is not being used.** A signal may already be collected and never applied. Name what the capability would do with it, and for whom.
- **A quality ceiling is set by the method, not the effort.** More care may not improve a result that a different technique would improve structurally. Propose the technique and the check that it helps here.
- **Two systems could be connected.** An integration may remove a manual bridge nobody counts. Use it when the connection's operational burden is stated alongside its saving.

## When not to use
- **The detail is untied to an outcome.** Implementation preferences without a value claim are not possibilities.
- **The technology was chosen for novelty.** Interest is not a constraint that needs removing.
- **The user or system need is unclear.** A capability serving no identified need cannot be evaluated.
- **The capability is known and merely needs building.** Execution of a settled choice is not exploration.
- **The concern is how people experience the result.** Experience arguments belong with the experience.
- **The claim is that it already works.** Whether something performs as stated is a check, not a possibility.

Route the suggestion elsewhere when one of those signals holds. Experience of the result belongs to product and experience, and a claim of current behaviour belongs to verification. A settled capability that needs building belongs to continuation, and a reusable asset with named consumers belongs to leverage. A commercial mechanism belongs to business and growth, and a large, uncertain, concentrated commitment belongs to big bets. If the feasibility question is the whole of the suggestion, use experiment so the spike gets a decision rule.
