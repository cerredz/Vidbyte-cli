# Completion

## Description
A completion suggestion closes a specific unfinished obligation that still matters to the current task. It turns an open loop into a defined final action, acceptance check, and stopping point. The obligation may be a missing deliverable, unresolved decision, final review, handoff, or cleanup step. The suggestion should distinguish genuine completion from polishing or adding new scope. It should make the remaining gap visible and small enough to close. Use this category when finishing the current work creates more value than starting another direction.

## Why use / use cases
- [ ] **A deliverable is almost usable.** One known omission may be preventing the work from being accepted or used. Suggest completion when the missing part is specific and the acceptance condition is already knowable.
- [ ] **A decision is still open at the finish line.** The work may be technically done but blocked by one unresolved choice. Use this category when recording and making that choice would close the obligation rather than expand the problem.
- [ ] **A final review has not happened.** A focused review may be the last condition before release or handoff. Recommend completion when the review scope is bounded and its findings have an owner and response path.
- [ ] **A handoff lacks one required artifact.** Another person or system may be waiting for instructions, credentials, context, or a summary. Use it when supplying the exact missing item transfers responsibility cleanly.
- [ ] **A validation result has not been recorded.** The work may have been checked informally but lacks an observable completion record. Suggest the smallest evidence capture that makes the state durable.
- [ ] **Cleanup is required to make the result safe to leave.** Temporary files, flags, access, or stale branches may remain after the main work. Use this category when cleanup is a real completion condition, not a general tidiness preference.
- [ ] **The current work is producing new open loops.** A short closeout pass may prevent unfinished decisions from becoming future confusion. Recommend it when the pass has a defined inventory and finish condition.
- [ ] **A stopping point is available now.** More improvement is possible, but the current result already meets the intended threshold. Use completion to identify the evidence that justifies closing rather than continuing to polish.

## Things to consider
- What exact obligation remains unfinished?
- Who or what is waiting for it to be closed?
- What observable acceptance condition proves completion?
- Which parts are required, and which are optional polish?
- What decision, artifact, review, or cleanup is the final gap?
- Can the remaining work be completed without reopening settled scope?
- What handoff or record makes the completed state durable?
- What explicit stopping point prevents completion from becoming expansion?

## Generation requirements

Every completion suggestion must close a specific obligation already inside the caller's commitment.
The proposal should:

- Name the remaining deliverable, decision, verification, communication, artifact, or handoff.
- Connect that missing piece to the original outcome and explain why finishing it makes “done” honest.
- Distinguish the final gap from polish, expansion, new capability, or a separate opportunity.
- Define an inspectable endpoint that another person can recognize without relying on the author's intent.
- Use supplied context to identify what is complete, in progress, blocked, or still unverified.
- Respect prerequisites, permissions, quality, safety, and acceptance conditions that must hold before
  closure.
- Keep the action sequence narrow enough to finish without reopening the entire project.
- State what evidence, review, recipient, or status change will confirm completion.
- Define how the suggestion handles a missing condition: obtain it, escalate it, or record why closure
  cannot yet be claimed.
- Keep closing the current obligation as the primary mechanism; route new direction, learning, or
  additional scope to other categories.

## Candidate shape

Shape the candidate as a final-gap closure with a visible endpoint. It should help an executor move
from current status to honest completion without converting the last step into another project.

- In the **summary**, name the incomplete obligation, original outcome, and reason this step closes it.
- In the **action sequence**, inspect the gap, perform the smallest remaining work, verify the result,
  and communicate or hand off the finished state.
- In **decision points**, choose acceptance evidence, scope boundary, recipient, escalation path, and
  the condition under which completion must be deferred.
- In **considerations**, cover quality, correctness, missing dependencies, reviewability, user impact,
  reversibility, communication, and scope creep.
- In **dependencies**, name a prerequisite, reviewer, artifact, permission, source, or decision needed
  to close the obligation.
- In **evidence references**, cite the stated goal, accepted criteria, current status, or blocker;
  do not cite intention as proof of completion.
- In **assumptions**, label what remains unknown and explain whether it can be checked within the
  completion action.
- In the **completion criterion**, require an observable final state, not merely an attempted action.
- If the final gap cannot be closed safely, return a bounded blocker resolution or explicit deferment.

## Valid suggestion directions

Use this category for concrete closure moves:

- Finish the missing implementation, document, decision, test, or handoff.
- Verify an acceptance condition that must be true before claiming completion.
- Resolve the last unresolved reviewer, stakeholder, or dependency response.
- Package or publish the artifact where delivery is part of the commitment.
- Record the final status, evidence, and owner so another person can inspect it.
- Communicate a completed result and any remaining limitation to the affected recipient.
- Close a cleanup, migration, or follow-up obligation explicitly included in the goal.
- Replace “almost done” with a checklist of only the remaining necessary conditions.
- Escalate or defer a final gap when authority or prerequisite is genuinely unavailable.
- Define the smallest honest stopping point when full polish is outside scope.

## Alignment check

The candidate is aligned when it closes a specific existing obligation and produces a recognizable
endpoint for the stated commitment. It should reduce the distance to “done,” not create a new reason
to continue. Completion can include verification, communication, or handoff when those are part of
the promised result.

Reject or reroute candidates that:

- Add a capability, audience, or improvement not required by the current commitment; use another category.
- Advance an accepted plan without closing its final obligation; use continuation.
- Require a missing condition whose resolution must come first; use prerequisite or investigation.
- Reopen a goal or direction that was not settled; use goal clarification, alternative, or strategy.
- Stop work because it is inconvenient rather than because the commitment is complete or no longer worth it.

The primary decision must be whether this is the smallest honest path to calling the current commitment done.

## When not to use
Do not use this category when the work is blocked by a missing prerequisite or unresolved uncertainty that must be investigated first. Avoid it when the proposed action creates a new capability instead of closing the current obligation. If the next action advances an accepted plan without being the final gap, use continuation; if the work no longer deserves attention, use stop or defer.
