**Max Total Tokens**
Max Total Tokens bounds the aggregate model usage scheduled across the whole workflow.
It covers initial generation, independent critique, and every permitted curation turn together.
The threshold stops new work after observed usage reaches the boundary but does not interrupt an active request.
Small overruns are therefore possible and should not be interpreted as ignored policy.
Reaching the cap returns the last committed snapshot with an explicit partial-result reason.

**Purpose of Max Total Tokens**
The purpose of Max Total Tokens is to give the caller one explicit ceiling over total token spend.
That ceiling keeps token-hungry runs with large contexts or many rounds inside a known allowance.
It also makes cost predictable before any model work starts, because the worst-case spend is bounded up front.
The cap works alongside the independent turn, edit, round, and time limits rather than replacing them.
When observed usage reaches the cap, the run stops with the `token_limit` stop reason and the last committed snapshot.

**When not to use Max Total Tokens**
Do not set Max Total Tokens merely because the option exists when the caller tracks spend elsewhere.
Omit it when the caller has no token allowance to enforce and let turns run under the other budgets.
Do not use this cap to bound a single reply, because the per-turn output ceiling governs reply size.
Use a narrower budget option when the concern is specifically turns, tool edits, rounds, or elapsed seconds.
Avoid a cap below the cost of one full generation turn, because the run would stop before producing anything.

**Max Total Tokens inputs**
The value is one positive integer up to 20000000 whenever it is specified.
A single value is supplied per run, and repeated occurrences are not combined into a larger allowance.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than an aggregate token ceiling for this run.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Max Total Tokens**
When it is omitted, no aggregate ceiling is enforced and usage is only observed and reported.
Command-line values are the only source for this cap, and the run does not read a separate configuration document.
Environment variables do not silently populate this budget, which keeps an invocation reproducible.
An explicit value always takes precedence over omission for exactly one run.
The per-turn output ceiling, when set, still shapes each reply independently of this aggregate cap.

**Max Total Tokens output contract**
Max Total Tokens is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective cap and the observed usage travel inside the result envelope.
For dry-run output, the manifest records the requested cap without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the stop reason, usage, and warnings.
A capped stop reports `token_limit` with the committed snapshot, so partial completion cannot resemble ordinary success.

**How to use Max Total Tokens**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the cap bounds spend rather than defining the task.
Budget from the request shape by multiplying expected turns by a realistic per-turn token cost.
Narrow categories and smaller context payloads lower every turn's input cost when the cap binds.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-total-tokens 200000
```

**Examples for Max Total Tokens**
A minimal example supplies only the required goal and leaves the aggregate spend unbounded by this cap.
A normal example sets a moderate allowance that covers generation, critique, and two curation passes.
An advanced example raises the allowance for extra compute across many categories with large evidence.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect usage, stop reason, and warnings.
If an example fails, preserve the same goal and correct the named budget before changing the reasoning settings.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-total-tokens 100000
vidbyte-cli --json agents suggest run --goal "{goal}" --max-total-tokens 1000000 --extra-compute
```

**Related commands for Max Total Tokens**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --max-output-tokens when the concern is per-turn reply size rather than aggregate spend.
Use --max-agent-calls when the concern is turn count rather than token volume.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Max Total Tokens**
A non-positive or oversized value fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded allowance.
Reaching the cap mid-run is not an error: the run returns the committed snapshot with the `token_limit` reason.
A provider or schema failure is reported as a provider failure and is never converted into a false budget stop.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Max Total Tokens**
This cap itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The cap limits how much of the caller's provider budget one run may spend but does not change what any turn may do.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the budget contract.
