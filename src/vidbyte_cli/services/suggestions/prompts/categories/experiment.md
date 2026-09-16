# Experiment

## Description
An experiment is a bounded intervention designed to separate competing explanations, designs, or choices. Its worth is measured entirely by whether the result would change what happens next, which means a test whose every outcome leads to the same action is not an experiment but a formality. The intervention must be small enough to run reversibly and specific enough to produce evidence that can be interpreted without argument. It must name the uncertainty it addresses, because the most common failure in this category is a rollout described as learning. A rollout gathers data while committing; an experiment gathers data in order to decide whether to commit. The difference is whether the decision is still open when the result arrives.

The suggestion should identify which competing accounts make different predictions, since discrimination between them is what the design has to achieve. It should name the baseline, comparison, or observation that makes the result interpretable, because a measurement with nothing to compare against usually confirms whatever was expected. It should specify enough sample, duration, or exposure for the question being asked, and admit when that is more than the situation can afford. It should constrain harms, spillovers, and irreversible commitments, since a test that damages what it was protecting has failed regardless of its result. It should set thresholds in advance for adoption, revision, further testing, and stopping, because effort already spent is the reason indefinite tests continue. It should state what the caller will do differently for each plausible result, and if that list has one entry, the experiment should not be run.

## Why use
Use this category when a decision is blocked by uncertainty that argument cannot resolve and evidence can. This is a narrower situation than it appears, because a great deal of hesitation is really about preference, authority, or unclear goals, none of which a test can settle. When the blocker genuinely is a fact about the world that nobody knows, an experiment converts an unresolvable debate into a scheduled answer, and that conversion is the most valuable thing the category offers.

The category also buys down the cost of being wrong. A consequential choice made without evidence carries the full cost of reversal; the same choice made after a bounded test carries the cost of the test plus a smaller probability of reversal. Where that trade is favourable it is strongly favourable, and it is favourable most often when commitment is expensive and testing is cheap. Naming the loss limit, the exposure, and the stop rule is what keeps the test on the cheap side of that trade.

Distinguish it from its close neighbours carefully, because they are routinely confused. Verification checks a claim believed to be true before something is relied on, which is a confirmation task rather than a discrimination task. Investigation gathers existing evidence to inform a decision without intervening in the world at all, and where the answer can be looked up, intervening is waste. Alternative compares routes by argument and is the right move when the distinguishing criteria are already known. Big bets concerns commitments too large for a test to substitute for, though staging often turns one into a sequence of experiments. Use experiment when a bounded intervention, and only an intervention, would change the decision.

## Use cases
- **Two explanations predict different outcomes.** Both accounts may fit the evidence available today. Design one bounded intervention whose result they disagree about.
- **A consequential design choice is uncertain.** Full commitment may be costly or hard to reverse. Test the behaviour that matters before the decision becomes expensive.
- **A new intervention needs evidence of effect.** The question may be whether a change improves a meaningful outcome at all. Use a comparison or baseline that makes the effect interpretable.
- **A feasibility question blocks a larger plan.** The issue may be whether a capability, process, or constraint can work at all. Test the limiting condition rather than building the whole solution.
- **A message or offer needs behavioural evidence.** Stated opinions may not predict whether people act, understand, or pay. Use a small exposure that measures the behaviour rather than the sentiment.
- **A process change may carry hidden costs.** Faster or simpler work can affect quality, safety, workload, or downstream flow. Run a limited rollout that observes the intended gain and the most likely harm together.
- **A stop rule is needed before more is invested.** Without a predefined threshold, a test continues because effort has already been spent. Define in advance what escalates, changes, or ends the effort.
- **A trial preserves options while learning.** A low-exposure test may avoid premature commitment to one route. Recommend it when both the exposure and the interpretation are controlled.
- **Estimates disagree by more than they should.** Two credible forecasts may differ enough that planning cannot proceed. Measure the quantity directly when measuring is cheaper than reconciling.
- **A rare failure needs to be reproduced.** An intermittent problem may resist analysis until it can be triggered deliberately. Design the smallest intervention that provokes it under observation.
- **A dependency's real behaviour is unknown.** Documentation, a vendor claim, or an assumption may not match practice under the conditions that matter. Probe it in the conditions that matter, not in general.
- **A capacity or scaling limit is assumed rather than known.** The plan may rest on a number nobody has measured. Test at the boundary before designing around it.

## When not to use
- **The needed action is already known.** Testing a settled decision spends time buying nothing.
- **The question is factual and answerable without intervening.** If it can be looked up, intervening is the expensive route.
- **No result would change the decision.** A test with one possible consequence is a ritual.
- **The proposal is an unbounded rollout.** Committing while measuring is not learning, whatever it is called.
- **The check merely confirms an established claim.** Confirmation before reliance is a different discipline with different standards.
- **The exposure cannot be constrained.** A test that risks the thing it protects has already failed.

Route the suggestion elsewhere when one of those signals holds. Confirming a claim before relying on it is verification, and gathering existing evidence is investigation. Comparing known routes by argument is alternative, and choosing a coordinating direction is strategy. A commitment too large to be substituted by a test is big bets, and execution of a settled decision is continuation. If the uncertainty is about what people experience rather than what the system does, use feedback.
