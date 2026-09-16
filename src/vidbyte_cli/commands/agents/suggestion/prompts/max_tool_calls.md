**Max Tool Calls**
Max Tool Calls is the run-local cap on store tool invocations the curation agent may attempt.
It covers adding or updating a suggestion, removing one by stable identifier or displayed number, and requesting bounded more-suggestions guidance.
The default of 64 calls comfortably covers several additions, updates, and guidance requests across the default rounds.
Callers lower it for tightly bounded edits and raise it when the curator is expected to reshape a large slate.
The store counts each attempted call before executing it, so a configured cap is never exceeded.

**Purpose of Max Tool Calls**
The purpose of Max Tool Calls is to bound what the tool-enabled curator can change in one run.
That bound keeps a runaway curation pass from churning the slate with unbounded edits.
It also protects the transaction boundary, because a rejected call cannot mutate committed state or bypass validation.
The cap works alongside the agent-call, token, time, and round limits rather than replacing them.
When the next tool call would exceed the cap, curation stops with the `tool_call_limit` stop reason and the last committed snapshot.

**When not to use Max Tool Calls**
Do not set Max Tool Calls merely because the option exists when the default already fits the slate size.
Omit it when the caller has no real editing constraint and let the default cover the standard curation passes.
Do not use this cap to control idea count, output length, or model turns, because dedicated options govern each of those.
Use a narrower budget option when the concern is specifically tokens, turns, or elapsed seconds.
Avoid setting the cap to 1 for real refinement, because a single guidance request can consume the whole budget.

**Max Tool Calls inputs**
The value is one integer between 1 and 4096 inclusive.
A single value is supplied per run, and repeated occurrences are not combined into a larger budget.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than a tool-call ceiling for this run.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Max Tool Calls**
When it is omitted, the default is 64 calls, which preserves the historical store behavior for uncapped runs.
Command-line values are the only source for this cap, and the run does not read a separate configuration document.
Environment variables do not silently populate this budget, which keeps an invocation reproducible.
An explicit value always takes precedence over the default for exactly one run.
The budget is run-local: working copies share it with the committed store, and uncommitted edits never refund it.

**Max Tool Calls output contract**
Max Tool Calls is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective cap travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested cap without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the stop reason and warnings.
A capped stop reports `tool_call_limit` with the committed snapshot, so partial completion cannot resemble ordinary success.

**How to use Max Tool Calls**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the cap is a budget rather than a standalone task.
Size the cap from the expected editing pattern, allowing several calls per idea the curator should touch.
Keep the agent-call cap high enough to cover the curation turns the larger tool budget permits.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-tool-calls 64
```

**Examples for Max Tool Calls**
A minimal example supplies only the required goal and leaves this budget at its default.
A normal example sets a modest cap that still covers a few additions and one update.
An advanced example raises the cap into the hundreds for reshaping a large slate across three rounds.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect the stop reason, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named budget before changing the reasoning settings.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-tool-calls 16
vidbyte-cli --json agents suggest run --goal "{goal}" --max-tool-calls 256 --rounds 3
```

**Related commands for Max Tool Calls**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --max-agent-calls when the concern is total model turns rather than curation edits.
Use --max-total-tokens when the concern is token spend rather than edit count.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Max Tool Calls**
A value outside 1 through 4096 fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded budget.
Reaching the cap mid-curation is not an error: the working copy is discarded and the committed snapshot returns with the `tool_call_limit` reason.
A provider or schema failure is reported as a provider failure and is never converted into a false budget stop.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Max Tool Calls**
This budget itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The cap limits how many store edits one run may attempt but does not change which edits validation will accept.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the budget contract.
