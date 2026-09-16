# Experiment

## Description
An experiment is a bounded intervention that separates competing explanations, designs, or choices. It is valuable only when its result can change what the caller does next. The test should be small enough to run reversibly and specific enough to produce interpretable evidence. A useful experiment names the uncertainty rather than disguising a rollout as learning. It should protect people, resources, and existing progress from unnecessary exposure. The result deserves a predefined decision rule so the test does not become indefinite activity.

## Why use / use cases
- [ ] **Two explanations predict different outcomes.** The caller may be unable to choose because both accounts fit the current evidence. Use an experiment when one bounded intervention can distinguish their predictions.
- [ ] **A design choice is consequential but uncertain.** A full commitment would be costly or hard to reverse. Suggest a smaller test that exposes the relevant behavior before the decision becomes expensive.
- [ ] **A new intervention needs evidence of effect.** The caller may want to know whether a change improves a meaningful outcome. Use the category when a comparison or baseline can make the effect interpretable.
- [ ] **A feasibility question blocks a larger plan.** The issue may be whether a capability, process, or constraint can work at all. Recommend an experiment that tests the limiting feasibility condition rather than building the whole solution.
- [ ] **A message or offer needs behavioral evidence.** Opinions may not predict whether people act, understand, or pay. Use this category when a small exposure can measure the behavior that matters.
- [ ] **A process change may create hidden costs.** Faster or simpler work could affect quality, safety, workload, or downstream flow. Suggest an experiment when a limited rollout can observe both the intended gain and the main harm.
- [ ] **The caller needs a stop rule before investing more.** Without a predefined threshold, a test can continue because effort has already been spent. Use the category to define what result escalates, changes, or ends the effort.
- [ ] **A low-risk trial preserves multiple options.** The caller may learn while avoiding a premature commitment to one route. Recommend an experiment when the trial’s exposure and interpretation are both controlled.

## Things to consider
- What single uncertainty or decision is the experiment meant to inform?
- Which competing explanations, interventions, or choices make different predictions?
- What is the smallest intervention that can discriminate among them?
- What baseline, comparison, or observation makes the result interpretable?
- What sample, duration, or exposure is enough for the question?
- What harms, spillovers, or irreversible commitments must be constrained?
- What thresholds trigger adoption, revision, further testing, or stopping?
- What will the caller do differently for each plausible result?

## Generation requirements

Every experiment suggestion must turn an uncertainty into a bounded test whose result changes a real
decision. The proposal should:

- State the hypothesis, mechanism, audience or system, and decision that depends on the result.
- Identify the smallest intervention that can distinguish the relevant outcomes without pretending it
  predicts every future condition.
- Define what is changed, what is held constant, who or what is observed, and over what period.
- Specify support, failure, ambiguity, and stop conditions before the test begins.
- Use supplied context to establish the problem and constraints; label causal assumptions explicitly.
- Avoid testing a vague preference, a completed claim, or a broad rollout disguised as an experiment.
- Account for safety, ethics, privacy, selection bias, operational burden, and effects on existing work.
- Assign an owner and define how results will be recorded and interpreted.
- State what the caller will do differently for each plausible result.
- Keep learning that changes action as the primary mechanism; route factual checks to verification or
  investigation and broad route choices to strategy or alternative.

## Candidate shape

Shape the candidate as a decision-linked hypothesis with a testable intervention and a precommitted
interpretation. The reader should know what is learned, not merely what activity is performed.

- In the **summary**, name the uncertainty, proposed intervention, and decision the result will inform.
- In the **action sequence**, state the hypothesis, design the smallest fair test, run it, inspect the
  result, and choose the next action.
- In **decision points**, choose sample or setting, treatment, comparison, duration, metric, thresholds,
  and what ambiguity requires another test.
- In **considerations**, cover signal quality, confounding, safety, cost, representativeness, ethics,
  reversibility, and operational disruption.
- In **dependencies**, name data, participants, access, instrumentation, owner, or authority required.
- In **evidence references**, cite the problem and prior observations; do not cite expected outcomes as
  if they were measured.
- In **assumptions**, label causal, behavioral, and measurement assumptions with a falsifying observation.
- In the **completion criterion**, require a recorded result and a decision to adopt, revise, repeat, or
  stop rather than a completed test with no interpretation.
- If the claim can be checked directly without changing an intervention, use verification or investigation.

## Valid suggestion directions

Use this category for bounded tests:

- Compare two routes, messages, interfaces, offers, or sequences against the same outcome.
- Run a small pilot before a broader rollout or irreversible commitment.
- Test whether a suspected constraint or intervention changes an observable behavior.
- Use a fake-door, concierge, prototype, cohort, or staged exposure when appropriate and ethical.
- Vary one consequential mechanism while preserving relevant context.
- Test adoption, comprehension, trust, retention, quality, cost, or operational feasibility.
- Measure a leading signal that can change the next decision before final outcomes arrive.
- Add a recovery or stop condition when the intervention could harm customers or the system.
- Repeat only when the first result is ambiguous and the next test reduces a named uncertainty.

## Alignment check

The candidate is aligned when an intervention is deliberately introduced to learn something that will
change the caller's next decision. It must define the hypothesis, boundaries, result interpretation,
and action for plausible outcomes. A test is not an experiment if the result cannot alter the plan.

Reject or reroute candidates that:

- Check an existing claim against an authoritative source; use verification.
- Gather facts without changing an intervention; use investigation.
- Execute a known action with no uncertainty; use continuation or immediate next steps.
- Explore many possibilities without a selected hypothesis; use creative exploration.
- Choose a broad direction rather than test one consequential uncertainty; use strategy or alternative.

The primary decision must be what the experiment will make possible to choose, stop, or change.

## When not to use
Do not use this category when the needed action is already known and merely needs execution or when the question is factual and can be answered by investigation. Avoid it when no result would change the decision or when the proposed “test” is actually an unbounded rollout. If the check is intended only to confirm an established claim, use verification; if the unresolved choice concerns the broader direction, use strategy or alternative.
