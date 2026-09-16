"""Central store for every warning the suggestion workflow can emit.

Each guardrail owns two texts. The short string is the stable operator-facing
warning kept on the versioned result. The guidance builder returns the long
model-facing text that tells the consuming model exactly what happened to the
run and what to do next. Guidance travels to a model in two ways: it is
injected into the next curator prompt while the run still has rounds left, and
it is appended beside its short warning when a guardrail ends the run, so the
JSON result envelope carries the recovery instructions to the calling agent.
"""

from __future__ import annotations

SHORT_TOOL_CALL_LIMIT = (
    "Curation reached its tool-call limit; returning the last committed suggestions."
)
SHORT_CURATION_FAILED = "Curation did not complete; returning the last committed suggestions."
SHORT_CURATION_INCOMPLETE = (
    "Curation returned an incomplete receipt; returning the last committed suggestions."
)
SHORT_AGENT_CALL_LIMIT = (
    "The run reached its agent-call limit; returning the last committed suggestions."
)
SHORT_TOKEN_LIMIT = (
    "The run reached its total-token limit; returning the last committed suggestions."
)
SHORT_TIME_LIMIT = "The run reached its time limit; returning the last committed suggestions."


def short_count_shortfall(returned: int) -> str:
    """Build the stable shortfall warning for a finalized idea count."""
    if type(returned) is not int or returned < 0:
        raise ValueError("Suggestion shortfall count must be a non-negative integer.")
    return f"Only {returned} worthwhile suggestions survived review; no filler was added."


def prompt_with_guidance(prompt: str, guidance: str) -> str:
    """Attach retry guidance to the next model turn without touching CLI streams."""
    if type(prompt) is not str or not prompt.strip():
        raise ValueError("Suggestion prompt must be a non-empty string.")
    if type(guidance) is not str:
        raise TypeError("Suggestion guidance must be a string.")
    if not guidance:
        return prompt
    return f"{prompt}\n\n<Run Guidance>\n{guidance}\n</Run Guidance>"


def guidance_agent_call_limit(max_calls: int, completed_calls: int) -> str:
    """Explain an agent-call stop and how the model should continue from the snapshot."""
    if type(max_calls) is not int or max_calls < 1:
        raise ValueError("Suggestion agent-call cap must be a positive integer.")
    if type(completed_calls) is not int or completed_calls < 0:
        raise ValueError("Suggestion completed-call count must be a non-negative integer.")
    return "\n\n".join(
        (
            (
                f"This suggestion run stopped because it reached its agent-call limit of "
                f"{max_calls} turns after completing {completed_calls} turns. The limit "
                "covers every model turn in the run: the initial generation, each "
                "independent critique, and every tool-enabled curation pass. The workflow "
                "checked the budget before each new turn, so the configured cap was never "
                "exceeded. No error occurred in the provider or the tool surface; the run "
                "simply ran out of permitted turns before further refinement could happen. "
                "The ideas returned beside this warning are the last committed snapshot, "
                "and every one of them passed category, evidence, duplicate, and ranking "
                "validation."
            ),
            (
                "Treat the returned slate as final for this run instead of retrying the "
                "same request with the same budget. A retry with an identical agent-call "
                "cap will stop at the same boundary and return the same snapshot while "
                "spending the full budget again. The committed snapshot is safe to present "
                "to the caller, because copy-on-write isolation discarded every uncommitted "
                "working copy at the moment the limit was reached. Nothing the curator was "
                "drafting when the run stopped leaked into the result. The stop reason "
                "`agent_call_limit` on the result records exactly why refinement ended, so "
                "downstream logic can distinguish this deliberate budget stop from a "
                "provider failure or a schema failure."
            ),
            (
                "Follow these steps in order. First, read the returned ideas and their "
                "review summaries, and decide whether the slate already answers the "
                "caller's goal. Second, when the slate is sufficient, execute or present "
                "the highest-ranked ideas directly without scheduling another suggestion "
                "run. Third, when the slate is insufficient, start one new run with a "
                "higher `--max-agent-calls` value rather than repeating the capped run. "
                "Fourth, keep the new cap bounded and proportionate: each critique pass "
                "costs one critic turn plus one curation turn, so add roughly two turns "
                "per extra refinement round wanted. Fifth, prefer raising the round count "
                "only together with the agent-call cap, because an extra round without "
                "matching turns stops at this same limit. Sixth, inspect the result usage "
                "mapping to see how turns were distributed across generation, critique, "
                "and curation before choosing the new budget."
            ),
            (
                "Do not attempt to resume this exact run, because suggestion runs are not "
                "resumable and there is no checkpoint to continue from. Do not ask the "
                "curator to apply the previous critic feedback outside a new run, because "
                "the tool surface only exists inside a live curation pass. Do not lower "
                "the requested idea count as a workaround without understanding the "
                "shortfall, since fewer requested ideas still cost generation, critique, "
                "and curation turns. Do not interpret the partial status as a failure of "
                "any single idea: the ideas were kept because they survived independent "
                "critique, not because the run gave up on them."
            ),
            (
                "Avoid this stop in future runs by sizing the agent-call budget from the "
                "requested work: one generation turn, plus two turns per critique round, "
                "plus headroom for the extra-compute fan-out when it is enabled. The "
                "default cap of 64 turns covers the default generation plus three "
                "critique-and-curation passes with wide margin, so reaching the limit "
                "usually means the caller set an intentionally small cap for testing or "
                "enabled extra compute without raising the budget. Record the chosen cap "
                "and the observed turn distribution together so the next caller can see "
                "whether refinement or generation consumed the budget."
            ),
        )
    )


def guidance_tool_call_limit(max_calls: int) -> str:
    """Explain a tool-call stop and how the model should continue from the snapshot."""
    if type(max_calls) is not int or max_calls < 1:
        raise ValueError("Suggestion tool-call cap must be a positive integer.")
    return "\n\n".join(
        (
            (
                f"This suggestion run stopped its curation pass because the run-local "
                f"tool-call budget of {max_calls} calls was exhausted. The budget covers "
                "every store tool invocation the curation agent attempts: adding or "
                "updating a suggestion, removing a suggestion by stable identifier or "
                "displayed number, and requesting bounded more-suggestions guidance. The "
                "store counted each attempted call before executing it, so the configured "
                "cap was never exceeded. The working copy that was being edited when the "
                "cap ran out was discarded whole, which means no partially edited state "
                "leaked into the committed slate. The ideas returned beside this warning "
                "are the last fully committed snapshot from before this curation pass."
            ),
            (
                "Treat the returned slate as the best fully validated state available "
                "rather than as a broken draft. Every idea in it passed category "
                "validation against the selected taxonomy, evidence validation against "
                "the context manifest, duplicate suppression, and deterministic ranking. "
                "The stop reason `tool_call_limit` records exactly why curation ended, so "
                "downstream logic can distinguish this deliberate budget stop from a "
                "provider transport failure or a malformed model reply. The discarded "
                "working copy is unrecoverable by design, because committing a partially "
                "edited slate would violate the transaction boundary that keeps the "
                "result trustworthy."
            ),
            (
                "Follow these steps in order. First, read the returned ideas and decide "
                "whether the slate already answers the caller's goal without further "
                "curation. Second, when the slate is sufficient, present or execute the "
                "highest-ranked ideas directly and do not schedule another curation run "
                "for the same goal. Third, when the slate needs more refinement, start "
                "one new run with a higher `--max-tool-calls` value instead of retrying "
                "with the same cap. Fourth, size the new cap from the observed editing "
                "pattern: each added idea costs at least one store call, each update "
                "costs another, and exploratory removals add more, so allow several calls "
                "per idea the curator is expected to touch. Fifth, keep the agent-call "
                "cap high enough to cover the extra curation turns the larger tool budget "
                "permits. Sixth, review the critic feedback embedded in the run before "
                "rerunning, because repeated tool exhaustion on the same slate usually "
                "means the curator is churning rather than converging."
            ),
            (
                "Do not retry the same run with the same tool cap, because the same "
                "curation pass will exhaust the same budget at the same point. Do not "
                "attempt to reconstruct the discarded working copy from memory, because "
                "its edits were never validated and may reference categories or evidence "
                "that validation would have rejected. Do not split one logical curation "
                "into many tiny runs to dodge the cap, since each run re-spends "
                "generation and critique turns. Do not treat the partial status as proof "
                "that the ideas are low quality: they are the ideas the independent "
                "critic already reviewed, not leftovers."
            ),
            (
                "Avoid this stop in future runs by granting the curator a tool budget "
                "proportionate to the slate size: the default cap of 64 calls comfortably "
                "covers several additions, updates, and guidance requests across the "
                "default rounds. Reaching the limit with default settings usually signals "
                "a curator stuck in an add-remove loop, which is better fixed by "
                "tightening the goal or the selected categories than by raising the cap "
                "without bound. Keep tool budgets run-local and bounded so one runaway "
                "curation pass can never consume unbounded provider resources."
            ),
        )
    )


def guidance_curation_failed(remaining_rounds: int) -> str:
    """Explain a curation provider failure and what the model should attempt next."""
    if type(remaining_rounds) is not int or remaining_rounds < 0:
        raise ValueError("Suggestion remaining-round count must be a non-negative integer.")
    return "\n\n".join(
        (
            (
                "This curation pass did not complete because the provider call behind it "
                "raised an error, and the workflow preserved the last committed snapshot "
                "instead of the failed pass. The failure happened inside the tool-enabled "
                "generator turn: a transport error, a timeout, a schema violation, or an "
                "unexpected exception from the agent surface. None of those outcomes say "
                "anything about the quality of the committed ideas, which had already "
                "passed independent critique before this pass started. The working copy "
                "for the failed pass was discarded whole, so no half-applied edit, no "
                "unvalidated draft, and no tool side effect survived into the committed "
                "state. The short warning recorded beside the result marks exactly which "
                "pass failed."
            ),
            (
                f"There are {remaining_rounds} refinement rounds remaining after this "
                "pass, and the workflow will spend the next one attempting curation "
                "again with the same committed snapshot and fresh critic feedback. Treat "
                "the failure as transient until proven otherwise: a single failed pass "
                "inside an otherwise healthy run is most often a momentary provider "
                "issue rather than a systematic problem with the goal or the slate. The "
                "committed snapshot stays available as the safe fallback, so a second "
                "consecutive failure still ends the run with a validated partial result "
                "instead of an error. The stop reason on the final result will say "
                "`provider_failed` only when the last permitted round also failed; an "
                "eventual success reports the normal completed or shortfall reason."
            ),
            (
                "Follow these steps in order. First, continue the workflow into the next "
                "round without changing the goal, the categories, or the budgets, since "
                "the failure carried no information about any of them. Second, run the "
                "independent critic again on the unchanged committed snapshot so the "
                "retry curates against fresh feedback rather than stale instructions. "
                "Third, attempt exactly one more tool-enabled curation pass with the "
                "same store tools and the same transaction boundary. Fourth, when the "
                "retry succeeds, commit its working copy and continue the normal loop, "
                "treating the earlier failure as fully recovered. Fifth, when the retry "
                "also fails, stop spending provider turns and return the committed "
                "snapshot with the partial status. Sixth, report the failure through the "
                "result warnings rather than inventing replacement ideas outside the "
                "validated workflow."
            ),
            (
                "Do not retry the failed pass immediately inside the same round, because "
                "back-to-back attempts against a struggling provider multiply cost "
                "without new information. Do not widen the budgets in response to a "
                "provider failure, since the failure consumed no committed progress and "
                "the caps were not the cause. Do not add filler ideas to hide the failed "
                "pass: the result must contain only ideas that survived critique, even "
                "when that leaves fewer ideas than requested. Do not reinterpret a "
                "provider failure as critic feedback about idea quality, because the two "
                "signals travel through different typed paths for exactly this reason."
            ),
            (
                "Avoid repeated failures by checking the provider configuration before "
                "scheduling another run after a fully failed workflow: credentials, "
                "model availability, and output token ceilings are the common systematic "
                "causes. A dry run validates the request shape, the context manifest, "
                "and the budgets without spending any provider turns, so use it to rule "
                "out request-side problems first. When failures persist across unrelated "
                "goals, treat the provider surface as degraded and stop launching capped "
                "runs until it recovers, rather than converting provider outages into "
                "rows of partial results."
            ),
        )
    )


def guidance_curation_incomplete(remaining_rounds: int) -> str:
    """Explain an incomplete curation receipt and what the model should attempt next."""
    if type(remaining_rounds) is not int or remaining_rounds < 0:
        raise ValueError("Suggestion remaining-round count must be a non-negative integer.")
    return "\n\n".join(
        (
            (
                "This curation pass returned an incomplete completion receipt, which "
                "means the tool-enabled generator finished its turn without confirming "
                "that the slate is useful. An incomplete receipt is a quality signal, "
                "not a transport failure: the provider answered, but the answer did not "
                "meet the structured contract the workflow requires before committing. "
                "The workflow therefore discarded the pass exactly as it discards a "
                "failed one, keeping the last committed snapshot untouched. The ideas "
                "returned beside the warning are the validated slate from before this "
                "pass, and their review summaries still describe the most recent "
                "successful critique."
            ),
            (
                f"There are {remaining_rounds} refinement rounds remaining after this "
                "pass, and the workflow will attempt curation again rather than giving "
                "up on refinement. Treat the incomplete receipt as feedback about the "
                "pass, not about the goal: the generator may have run out of output "
                "room, misunderstood the feedback payload, or stopped early on a "
                "difficult slate. The next round starts from the same committed snapshot "
                "with a fresh critic review, which gives the curator a second, cleaner "
                "problem statement. When the retry completes, its working copy commits "
                "normally and the earlier incomplete pass leaves no trace except the "
                "short warning. When every remaining round ends incompletely, the run "
                "returns the committed snapshot with the partial status."
            ),
            (
                "Follow these steps in order. First, advance to the next round without "
                "editing the goal or reselecting categories, because the receipt said "
                "nothing about either. Second, run the independent critic on the "
                "unchanged snapshot so the retry works from current feedback. Third, "
                "attempt one more curation pass with the same tools, watching for a "
                "completed receipt this time. Fourth, consider raising "
                "`--max-output-tokens` before a fresh run when incomplete receipts "
                "repeat, since a cramped output ceiling is the most common mechanical "
                "cause of truncated curation turns. Fifth, when the retry succeeds, "
                "commit and continue the normal loop as if the incomplete pass never "
                "happened. Sixth, never hand-craft a completion receipt outside the "
                "typed workflow to force progress."
            ),
            (
                "Do not commit any edit from the incomplete pass, because its receipt "
                "explicitly declined to vouch for the slate. Do not copy fragments of "
                "the incomplete pass into the next prompt as if they were validated, "
                "since uncommitted working state is untrusted by construction. Do not "
                "raise the agent-call or tool-call caps in response, because the pass "
                "consumed its normal turn and the caps did not cause the incompleteness. "
                "Do not present the incomplete pass as partial progress to the caller: "
                "only committed snapshots are presentable, and the warnings already "
                "record that a pass was skipped."
            ),
            (
                "Avoid repeated incomplete receipts by giving the curator enough output "
                "room and a focused slate: very large requested counts with tight output "
                "ceilings force the generator to choose between completeness and the "
                "receipt. Keep the requested count inside the validated range and leave "
                "the output token ceiling generous unless a real cost constraint says "
                "otherwise. When incompleteness persists across small slates and generous "
                "ceilings, treat the curator prompt or the model selection as the "
                "suspect and inspect the design documentation before rerunning."
            ),
        )
    )


def guidance_token_limit(max_tokens: int, observed_tokens: int) -> str:
    """Explain a total-token stop and how the model should continue from the snapshot."""
    if type(max_tokens) is not int or max_tokens < 1:
        raise ValueError("Suggestion total-token cap must be a positive integer.")
    if type(observed_tokens) is not int or observed_tokens < 0:
        raise ValueError("Suggestion observed-token count must be a non-negative integer.")
    return "\n\n".join(
        (
            (
                f"This suggestion run stopped because observed token usage reached "
                f"{observed_tokens} against a total-token cap of {max_tokens}. The "
                "counter accumulates provider-reported tokens across every completed "
                "turn: generation, critique, and curation alike. The workflow checked "
                "the budget before each new turn, so the cap stopped further spending "
                "without interrupting a turn already in flight. Small overruns past the "
                "cap are therefore possible and expected, and they do not indicate "
                "ignored policy. The ideas returned beside this warning are the last "
                "committed snapshot, fully validated and safe to present."
            ),
            (
                "Treat the returned slate as the spend-capped outcome of this run rather "
                "than as damaged output. Token accounting is independent of the turn "
                "counters, so this stop says the run spent its token allowance, not that "
                "it ran out of permitted turns or hit a provider error. The stop reason "
                "`token_limit` records exactly which budget ended the run, letting "
                "downstream logic separate cost control from quality problems. The "
                "committed snapshot carries no record of the turn that would have run "
                "next, because that turn was never created."
            ),
            (
                "Follow these steps in order. First, read the returned ideas and decide "
                "whether the slate already answers the caller's goal within the spent "
                "budget. Second, when the slate suffices, present or execute it directly "
                "without launching another token-consuming run. Third, when the slate "
                "needs more refinement, start one new run with a higher "
                "`--max-total-tokens` value rather than repeating the capped budget. "
                "Fourth, reduce token spend structurally where possible: narrower "
                "categories shrink the taxonomy block in every context window, fewer "
                "rounds remove whole critique-and-curation cycles, and smaller context "
                " payloads lower every turn's input cost. Fifth, keep the agent-call cap "
                "consistent with the token budget so the two limits tell one coherent "
                "spending story. Sixth, compare observed tokens against the usage "
                "mapping on the result to see which phase consumed the allowance."
            ),
            (
                "Do not retry with the same token cap, because the same workload will "
                "exhaust the same allowance at the same point. Do not disable the token "
                "cap entirely as a first resort: unbounded token spend is exactly the "
                "failure mode this guardrail exists to prevent. Do not confuse this stop "
                "with an agent-call stop when diagnosing the run; the usage mapping "
                "shows both counters precisely. Do not pad the next request with extra "
                "context to compensate, since larger context windows spend the new "
                "budget faster."
            ),
            (
                "Avoid this stop in future runs by budgeting tokens from the request "
                "shape: multiply the expected turn count by a realistic per-turn token "
                "cost that includes the full context window, not just the prompt. Large "
                "file attachments and wide category selections raise every turn's input "
                "cost, so bound them before raising the cap. Leave the token cap set "
                "whenever a run spends someone else's provider budget, and record the "
                "chosen cap beside the observed spend so the next caller can budget "
                "from evidence instead of guesses."
            ),
        )
    )


def guidance_time_limit(timeout_seconds: int) -> str:
    """Explain a wall-clock stop and how the model should continue from the snapshot."""
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ValueError("Suggestion timeout must be a positive integer.")
    return "\n\n".join(
        (
            (
                f"This suggestion run stopped because it reached its wall-clock timeout "
                f"of {timeout_seconds} seconds. The deadline spans the whole workflow "
                "from initial generation through the final curation pass, and the "
                "workflow checked the remaining time before each new turn. An in-flight "
                "provider call was allowed to finish or time out on its own rather than "
                "being killed mid-turn, so the committed snapshot was never left "
                "half-written. The ideas returned beside this warning are the last "
                "fully committed state from before the deadline, and each one passed "
                "the full validation chain."
            ),
            (
                "Treat the returned slate as the time-boxed outcome of this run rather "
                "than as expired work. A timeout says the run needed more wall-clock "
                "time than permitted, not that the ideas are stale or that the provider "
                "failed. The stop reason `time_limit` records exactly which boundary "
                "ended the run, so downstream logic can separate slow execution from "
                "budget exhaustion and transport errors. Any turn still in flight when "
                "the deadline arrived contributed nothing to the result, because only "
                "completed, committed passes shape the snapshot."
            ),
            (
                "Follow these steps in order. First, read the returned ideas and decide "
                "whether the slate already answers the caller's goal despite the "
                "shortened refinement. Second, when the slate suffices, present or "
                "execute it directly instead of spending another full timeout window. "
                "Third, when the slate needs more refinement, start one new run with a "
                "higher `--timeout-seconds` value rather than repeating the same "
                "deadline. Fourth, reduce wall-clock demand structurally where "
                "possible: fewer rounds remove whole critique-and-curation cycles, "
                "narrower categories shrink every context window, and disabling "
                "extra compute removes the parallel fan-out. Fifth, keep the token and "
                "agent-call caps consistent with the longer deadline so the run cannot "
                "trade a timeout for unbounded spend. Sixth, check whether provider "
                "latency rather than workload caused the overrun before changing the "
                "request shape."
            ),
            (
                "Do not retry with the same timeout when the workload is unchanged, "
                "because the same phases will need the same wall-clock time again. Do "
                "not remove the timeout entirely as a first resort: an unbounded run "
                "against a slow provider blocks the caller with no feedback. Do not "
                "interpret the partial status as a signal to hurry the next run by "
                "shrinking rounds and requested count together without thought, since "
                "that changes what the run can produce. Do not blend timeout handling "
                "with cancellation handling: a caller cancellation stays a typed "
                "provider concern and is never converted into a successful partial "
                "result."
            ),
            (
                "Avoid this stop in future runs by budgeting wall-clock time from the "
                "request shape: count the expected provider turns, multiply by a "
                "realistic per-turn latency observed on the chosen provider, and add "
                "headroom for retries and slow rounds. Extra compute multiplies "
                "generation latency across categories, so raise the timeout whenever it "
                "is enabled. Record the chosen deadline beside the observed phase "
                "timings so the next caller can distinguish a tight deadline from a "
                "degraded provider."
            ),
        )
    )


__all__ = [
    "SHORT_AGENT_CALL_LIMIT",
    "SHORT_CURATION_FAILED",
    "SHORT_CURATION_INCOMPLETE",
    "SHORT_TIME_LIMIT",
    "SHORT_TOKEN_LIMIT",
    "SHORT_TOOL_CALL_LIMIT",
    "guidance_agent_call_limit",
    "guidance_curation_failed",
    "guidance_curation_incomplete",
    "guidance_time_limit",
    "guidance_token_limit",
    "prompt_with_guidance",
    "short_count_shortfall",
]
