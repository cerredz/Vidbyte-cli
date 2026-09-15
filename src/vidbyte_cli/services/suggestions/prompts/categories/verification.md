# Verification

## Description
A verification suggestion tests a claim that matters to the caller’s next decision. The claim may concern requirements, evidence, behavior, readiness, safety, or the result of earlier work. The check should be narrower than the entire goal while still being relevant to the risk of proceeding. A useful verification states what would count as support, failure, or unresolved uncertainty. It should rely on an observable or authoritative source rather than repeating an assumption or relying on intent. Use this category when a focused check can make the status of a consequential claim more honest and actionable.

## Why use / use cases
- [ ] **A requirement is claimed to be satisfied.** The work may appear complete while one acceptance condition remains uncertain. Use verification to check the requirement directly before treating the result as done.
- [ ] **A result depends on an unconfirmed fact.** A decision may be safe only if a particular premise is true. Suggest a focused check when an authoritative source or observation can confirm the premise.
- [ ] **A behavior may differ from its intended design.** The caller may need to know what actually happens under a relevant condition. Use this category when a reproducible observation can establish the behavior.
- [ ] **Readiness is being asserted before exposure.** A release, handoff, launch, or migration may depend on a state that can be inspected. Recommend verification when the check can catch a consequential gap before commitment.
- [ ] **A previous fix may have worked only in the happy path.** The claim may need a boundary, failure, or representative case. Use it when testing the relevant edge is cheaper than discovering the gap later.
- [ ] **Evidence is being summarized without a source check.** A citation, measurement, or record may not support the conclusion being drawn. Suggest verification when tracing the claim to its source can change confidence or action.
- [ ] **Two parties disagree about current status.** A shared observation can resolve whether the disagreement is factual. Use this category when the check has an agreed source and does not require a broad negotiation.
- [ ] **A gate or policy must be demonstrated.** The caller may need evidence that a control, permission, or standard is actually satisfied. Recommend verification when the pass condition and evidence record are explicit.

## Things to consider
- What exact claim is being tested, and which decision depends on it?
- Why would being wrong matter at this point in the work?
- Which source, observation, test, or authority can establish the claim?
- What counts as support, failure, and unresolved uncertainty?
- Is the check narrow enough to perform but broad enough to represent the claim?
- What edge, boundary, or failure condition is most consequential?
- What decision follows from each result?
- What evidence should be retained so another person can inspect the status?

## When not to use
Do not use this category when the caller needs to discover an unknown fact through open-ended inquiry or test a new intervention whose effect is uncertain. Avoid it when the claim is too vague to define a pass condition or when the check cannot change the next decision. If a change must be tried to learn what happens, use experiment; if the current need is to close the remaining obligation, use completion.
