# Completion

## Description
A completion suggestion closes one specific unfinished obligation that still matters to the current task. It converts an open loop into a defined final action, an acceptance condition, and a stopping point. The obligation may be a missing deliverable, an unresolved decision, a final review, a handoff, a recorded result, or a cleanup step that makes the state safe to leave behind. What makes it a completion rather than more work is that the gap is the last one, and closing it changes the status of the whole from open to done. The category is narrow on purpose, because the failure it exists to prevent is the one where nearly finished work stays nearly finished indefinitely. Naming the remaining gap precisely is most of the value.

The suggestion must distinguish genuine completion from polish and from new scope, which are the two ways this category is usually misused. Polish improves something already sufficient; new scope adds capability that was never part of the obligation. Both feel like finishing and neither is. State the observable acceptance condition that proves the work is closed, since completion asserted without evidence tends to be re-litigated later. Name who or what is waiting, because an obligation with no waiting party is often not an obligation at all. Say what record or handoff makes the completed state durable, so the closure survives the attention of the person who created it. Give the stopping point explicitly, because without one the closing pass reliably becomes another round of improvement.

## Why use
Use this category when the highest-value action available is to finish rather than to start. Unfinished work carries a cost that is easy to underestimate: it holds context in someone's head, blocks whoever is downstream, and quietly accumulates until nobody can say what state anything is in. A suggestion that closes one obligation cleanly removes more drag than a suggestion that opens a promising new direction, and it is the less appealing recommendation, which is precisely why it needs a category of its own.

The category also enforces a definition of done that survives contact with optimism. Left unspecified, "finished" drifts towards whatever the person doing the work finds satisfying, and the same deliverable can be finished three times. Requiring an acceptance condition and a stopping point pins that definition to something observable. It converts a feeling into a check, which is what allows responsibility to transfer to someone else.

Distinguish it from the categories nearest to it. Continuation advances an accepted plan by its next bounded step, which may be one of many remaining; completion applies only when the gap being closed is the last one. Verification tests a claim that something is true, which may be part of completing but is argued from doubt rather than from an outstanding obligation. Quick wins looks for small, cheap value anywhere, where completion is specifically about the obligation already incurred. Stop or defer abandons the obligation rather than closing it, and it is the right category when finishing is no longer worth the remaining effort.

## Use cases
- **A deliverable is one omission from usable.** A single known gap may be all that stands between the work and acceptance. Suggest completion when the missing piece is specific and the acceptance condition is already knowable.
- **An open decision sits at the finish line.** The work may be technically done and blocked by one unmade choice. Use it when making and recording that choice closes the obligation rather than reopening the problem.
- **A final review has not happened.** A focused review may be the last condition before release or handoff. Recommend it when the review scope is bounded and findings have an owner and a response path.
- **A handoff is missing one artifact.** Another person or system may be waiting on instructions, credentials, context, or a summary. Use it when supplying that exact item transfers responsibility cleanly.
- **A result was checked but never recorded.** Work may have been validated informally and left without durable evidence. Suggest the smallest capture that makes the state observable to someone else.
- **Cleanup is a real completion condition.** Temporary files, feature flags, access grants, or stale branches may remain after the main work. Use the category when leaving them is a genuine hazard, not when tidiness is merely preferred.
- **The work is generating new open loops.** A short closeout pass may stop unfinished decisions from becoming future confusion. Recommend it when the pass has a defined inventory and a finish condition.
- **A stopping point is already available.** Further improvement is possible while the current result already meets the agreed threshold. Use completion to name the evidence that justifies closing instead of continuing.
- **Documentation required by the obligation is absent.** A runbook, a decision record, or an interface note may have been part of the agreed deliverable. Close it when the document was promised rather than merely desirable.
- **An approval or sign-off is outstanding.** The work may be waiting on a formal acceptance nobody has requested. Suggest requesting it explicitly, naming who signs and against what criteria.
- **A temporary measure needs to be retired or made permanent.** A workaround may be silently becoming the design. Use the category to force the choice and close the loop either way.
- **Partial results are unusable until assembled.** Several finished pieces may deliver nothing until someone integrates them. Recommend the assembly step when it is the final gap rather than a new build.

## When not to use
- **A prerequisite is missing.** Work blocked by an absent condition is not one step from done.
- **An unresolved uncertainty controls the outcome.** Closing around a question that has not been answered produces a false finish.
- **The proposed action adds capability.** New scope is not completion, however naturally it follows.
- **The action is polish on something already sufficient.** Improving a result past its threshold reopens work that was closed.
- **The step advances the plan without ending it.** A next move among several is continuation, not closure.
- **The obligation is no longer worth meeting.** Finishing work whose value has gone is an expensive way to feel tidy.

Route the suggestion elsewhere when one of those signals holds. A missing condition belongs to prerequisite, and an unanswered question belongs to investigation or verification. A next bounded step in an accepted plan is continuation, and abandoning the obligation is stop or defer. Added capability is usually continuation, alternative, or product and experience depending on what it changes. If the obligation is unclear because nobody agreed what finished means, the prior category is goal clarification.
