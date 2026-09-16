**Max Agent Calls**
Max Agent Calls is the run-wide cap on model turns that one suggestion run may spend.
It counts the initial generation turn, every independent critic turn, and every tool-enabled curation turn in a single shared budget.
The default of 64 turns covers the default generation plus several critique-and-curation passes with wide margin.
Callers lower it for cheap bounded probes and raise it when extra compute or extra rounds need more turns.
The workflow checks the budget before creating each new agent, so a configured cap is never exceeded.

**Purpose of Max Agent Calls**
The purpose of Max Agent Calls is to give the caller one explicit ceiling over total provider turns.
That ceiling keeps a run with recovery paths or extra compute from consuming unbounded calls.
It also makes spend predictable before any model work starts, because the worst-case turn count is known up front.
The cap works alongside the independent rounds, token, time, and tool-call limits rather than replacing them.
When the next turn would exceed the cap, the run stops with the `agent_call_limit` stop reason and the last committed snapshot.

**When not to use Max Agent Calls**
Do not set Max Agent Calls merely because the option exists when the default already fits the workload.
Omit it when the caller has no real cost constraint and let the default cover the standard rounds.
Do not use this cap to control output length, idea count, or wall-clock time, because dedicated options govern each of those.
Use a narrower budget option when the concern is specifically tokens, tool edits, or elapsed seconds.
Avoid setting the cap to 1 or 2 for real work, because generation alone needs its turn before any critique can happen.

**Max Agent Calls inputs**
The value is one integer between 1 and 2048 inclusive.
A single value is supplied per run, and repeated occurrences are not combined into a larger budget.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than a turn ceiling for this run.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Max Agent Calls**
When it is omitted, the default is 64 turns, which preserves the historical behavior of uncapped runs.
Command-line values are the only source for this cap, and the run does not read a separate configuration document.
Environment variables do not silently populate this budget, which keeps an invocation reproducible.
An explicit value always takes precedence over the default for exactly one run.
Other budgets such as rounds, tokens, timeout, and tool calls remain independent and are checked separately.

**Max Agent Calls output contract**
Max Agent Calls is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective cap travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested cap without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the stop reason and usage counters.
A capped stop reports `agent_call_limit` with the committed snapshot, so partial completion cannot resemble ordinary success.

**How to use Max Agent Calls**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the cap is a budget rather than a standalone task.
Raise the cap together with rounds when an extra refinement pass needs matching turns.
Add roughly two turns per extra critique round, since each round costs one critic turn plus one curation turn.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-agent-calls 64
```

**Examples for Max Agent Calls**
A minimal example supplies only the required goal and leaves this budget at its default.
A normal example sets a modest cap that still covers generation, critique, and one curation pass.
An advanced example raises the cap into the hundreds for extra compute across many categories.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect the stop reason, warnings, and turn counters.
If an example fails, preserve the same goal and correct the named budget before changing the reasoning settings.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-agent-calls 16
vidbyte-cli --json agents suggest run --goal "{goal}" --max-agent-calls 128 --rounds 3
```

**Related commands for Max Agent Calls**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --max-tool-calls when the concern is specifically curation edits rather than total model turns.
Use --max-total-tokens when the concern is token spend rather than turn count.
Use --timeout-seconds when the concern is wall-clock time rather than provider calls.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Max Agent Calls**
A value outside 1 through 2048 fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded budget.
Reaching the cap mid-run is not an error: the run returns the committed snapshot with the `agent_call_limit` reason.
A provider or schema failure is reported as a provider failure and is never converted into a false budget stop.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Max Agent Calls**
This budget itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The cap limits how many turns may spend the caller's provider budget but does not change what any turn may do.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the budget contract.
