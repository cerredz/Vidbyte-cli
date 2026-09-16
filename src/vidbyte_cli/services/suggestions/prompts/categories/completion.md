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
The category exists because unfinished work decays: an open loop keeps consuming attention, blocks the
people waiting on it, and slowly turns into a thing nobody can safely call finished. The requirement is
therefore precision about the gap — what exactly remains, why it is part of the promise rather than an
addition to it, and what closing it would let the caller stop carrying. The most common failure is
scope, because polish, extra capability, and nearby improvements all present themselves as finishing,
and each one moves the finish line. A completion suggestion must draw that boundary explicitly. It also
has to define an endpoint another person can inspect, since a status asserted only by the author is not
one anyone downstream can rely on. Where a condition needed for closure is missing, the honest move is
to obtain it, escalate it, or record why closure cannot yet be claimed. The proposal should:

- Name the remaining deliverable, decision, verification, communication, artifact, or handoff.
- Connect that missing piece to the original outcome and explain why finishing it makes the closure
  honest.
- Distinguish the final gap from polish, expansion, new capability, or a separate opportunity.
- Define an inspectable endpoint another person can recognize without relying on the author's intent.
- Respect prerequisites, permissions, quality, safety, and acceptance conditions that must hold before
  closure.
- Keep the action sequence narrow enough to finish without reopening the entire project.
- State what evidence, review, recipient, or status change will confirm completion.
- Define how a missing condition is handled: obtain it, escalate it, or record why closure cannot yet
  be claimed.
- Name who is waiting on the closure, so completion serves the obligation rather than the author's
  sense of tidiness.

## Alignment check

Alignment, for completion, means the candidate shortens the distance to an honest finish on something
the caller has already committed to. The obligation exists; what is missing is its last piece — a
deliverable, a decision, a check, a handoff, a message someone is waiting for. An aligned candidate
identifies that piece, keeps the action narrow enough to actually close it, and ends at a point another
person can inspect. The governing question is whether the work reduces what the caller still owes. A
candidate that adds to the obligation instead of discharging it, however useful the addition may be, is
not completion.

The second half of alignment is resisting the finish line's drift. Polishing, generalizing, and
handling one more case all feel like finishing and all extend the commitment, so an aligned candidate
states what it is deliberately not doing. Adding capability, audience, or improvement beyond the
current commitment belongs elsewhere; advancing an accepted plan that still has distance to run belongs
to continuation; a missing condition that must be resolved first belongs to prerequisite or
investigation; and reopening a goal or direction that was never settled belongs to goal clarification,
alternative, or strategy. Abandoning work because it has become inconvenient is stop or defer rather
than completion. Keep the candidate here only when it is the smallest honest path to calling the
current commitment finished.

## When not to use
Do not use this category when the work is blocked by a missing prerequisite or unresolved uncertainty that must be investigated first. Avoid it when the proposed action creates a new capability instead of closing the current obligation. If the next action advances an accepted plan without being the final gap, use continuation; if the work no longer deserves attention, use stop or defer.
