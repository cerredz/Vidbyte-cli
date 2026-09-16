# Risk Prevention

## Description
A risk-prevention suggestion reduces the likelihood or impact of a plausible failure. It connects a recognizable exposure to a proportionate guard, signal, or recovery plan. The suggestion should focus on risks that could change the caller’s outcome rather than every imaginable concern. Prevention is strongest when the protection happens before the exposure begins. Detection and recovery still matter when prevention cannot be complete or would cost too much. Use this category when the benefit of reducing the exposure outweighs the burden of the control.

## Why use / use cases
- [ ] **A known failure mode could derail the outcome.** The caller has enough context to describe how the failure would occur. Use this category when a specific guard can reduce the likelihood or impact before exposure grows.
- [ ] **An irreversible action is approaching.** A check, backup, approval, or staged release may preserve recovery before the point of no return. Suggest prevention when the protection is proportionate to the consequence.
- [ ] **A handoff can lose critical information.** Ambiguous ownership, missing context, or an unverified interface may create predictable failure. Use it to add a narrow contract or confirmation at the boundary.
- [ ] **A small control prevents expensive rework.** A validation, limit, default, or precondition may catch the issue earlier. Recommend it when the control cost is lower than repairing the downstream result.
- [ ] **Exposure is increasing faster than confidence.** The work may be reaching more users, systems, data, or stakeholders than the evidence supports. Use this category to add staged exposure or a leading signal.
- [ ] **Detection is too slow for the consequence.** The caller may need an alert, audit, or checkpoint before the failure compounds. Suggest prevention when faster detection creates a credible recovery window.
- [ ] **A fallback can preserve the core obligation.** The primary route may fail despite reasonable safeguards. Use it when a concrete alternate path or recovery state can reduce the impact.
- [ ] **A recurring incident needs a durable guard.** Repeated warnings or manual fixes may indicate that prevention belongs in the workflow. Recommend it when the pattern and owner of the control are clear.

## Things to consider
- What exact failure mode and exposure make the risk plausible?
- How severe, likely, observable, and reversible is the outcome?
- Which prevention point occurs before the exposure or commitment?
- What guard, limit, checkpoint, or default is proportionate?
- How will the control avoid creating equal or greater operational burden?
- What signal detects failure early enough to matter?
- What recovery or fallback preserves the core outcome?
- Who owns the control, monitors it, and revises it when conditions change?

## Generation requirements

Every risk-prevention suggestion must reduce the likelihood or impact of a plausible consequential
failure with a proportionate control. The proposal should:

- Name the exposure, trigger, affected outcome, and time when prevention matters.
- Explain likelihood, impact, detectability, or reversibility without inventing unsupported probabilities.
- Prefer prevention before exposure, while retaining detection, response, and recovery where prevention cannot be complete.
- Choose a control, owner, signal, or boundary that addresses the causal path rather than adding generic caution.
- Account for control burden, usability, accessibility, privacy, safety, and risks introduced by the control itself.
- Use supplied incidents, constraints, failure modes, or obligations; label hypothetical risks as assumptions.
- Define how the control will be monitored, tested, maintained, and revised as conditions change.
- Preserve necessary work while making the decision to accept, reduce, transfer, avoid, or monitor exposure explicit.
- State what signal would show the risk is reduced or the control is failing.
- Keep proportionate exposure reduction as the primary mechanism; route claim checks, bottlenecks, and abandonment decisions elsewhere.

## Candidate shape

Shape the candidate as a risk hypothesis with a control and recovery path. The reader should know what
could fail, how the intervention changes exposure, who owns it, and how effectiveness is observed.

- In the **summary**, name the risk, consequence, trigger, and proposed prevention or mitigation.
- In the **action sequence**, assess the exposure, choose a control, assign ownership, test it, and define response if it fails.
- In **decision points**, choose prevention versus detection, control strength, accepted residual risk, owner, and escalation.
- In **considerations**, cover severity, likelihood, detectability, burden, safety, privacy, access, false positives, and maintenance.
- In **dependencies**, name authority, monitoring, data, training, tooling, or recovery capability required for the control.
- In **evidence references**, cite prior failures, requirements, incidents, or observed exposure; do not cite anxiety as likelihood.
- In **assumptions**, label causal and severity assumptions with a check or monitoring signal.
- In the **completion criterion**, require the control to be in place and an observable signal or recovery rehearsal to pass.
- If no plausible consequence or owner exists, investigate or stop rather than adding a control.

## Valid suggestion directions

Use this category for proportionate safeguards:

- Prevent a known failure before a risky action, release, handoff, or exposure.
- Add validation, approval, isolation, fallback, rate limit, or recovery at the causal boundary.
- Detect a failure early enough to reduce impact and assign a response owner.
- Reduce blast radius, access, dependency, or irreversible commitment.
- Test a control under a representative edge or failure condition.
- Replace a fragile manual step with a safer repeatable guard where evidence supports it.
- Record accepted residual risk and the condition that would trigger stronger protection.
- Remove an exposure entirely when the cost of prevention is lower than its plausible consequence.
- Monitor control burden so protection does not create inaccessible or unsafe work.

## Alignment check

The candidate is aligned when it protects a valuable outcome from a plausible consequential failure and
defines a proportionate control, owner, and signal. It should address a specific exposure rather than
list every imaginable concern. Prevention is stronger when it acts before exposure begins.

Reject or reroute candidates that:

- Need to establish whether a claim is true; use verification.
- Reflect a repeated flow constraint rather than a failure exposure; use bottleneck.
- Have no plausible consequence, owner, or maintenance path.
- Should be abandoned because exposure cannot be justified; use stop or defer.
- Add generic warnings without changing likelihood, impact, detection, or recovery.

The primary decision must be which safeguard changes the risk path enough to justify its burden.

## When not to use
Do not use this category for every hypothetical concern, a goal that is merely unclear, or a claim that needs verification rather than protection. Avoid it when the control burden exceeds the plausible consequence or when no owner can maintain it. If the right answer is to abandon an exposure entirely, use stop or defer; if the risk comes from one limiting constraint, use bottleneck.
