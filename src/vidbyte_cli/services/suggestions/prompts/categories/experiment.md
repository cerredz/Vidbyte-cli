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

## When not to use
Do not use this category when the needed action is already known and merely needs execution or when the question is factual and can be answered by investigation. Avoid it when no result would change the decision or when the proposed “test” is actually an unbounded rollout. If the check is intended only to confirm an established claim, use verification; if the unresolved choice concerns the broader direction, use strategy or alternative.
