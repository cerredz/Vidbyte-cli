**Rounds**
Rounds is the number of critique-and-curation passes that may improve the active suggestion slate.
Two rounds usually balance refinement against latency and model usage for ordinary goals.
A single round suits simple goals with clear context, while three allows borderline ideas another curation opportunity.
The workflow computes this loop shape in code rather than asking the model when to stop.
Initial generation happens once before the first round, so rounds count refinement passes only.

**Purpose of Rounds**
The purpose of Rounds is to bound how many times the slate cycles through independent review and tool-enabled repair.
That bound keeps refinement effort predictable and prevents endless polish loops over the same candidates.
It also gives each round a stable meaning: fresh critic feedback followed by one isolated curation attempt.
The limit works alongside the agent-call, tool-call, token, and time budgets rather than replacing them.
When the final round completes with committed edits, the run stops with the `round_limit` reason.

**When not to use Rounds**
Do not raise Rounds merely because more passes sound better when two already converge on a useful slate.
Omit it when the caller has no refinement requirement and let the default of two passes apply.
Do not use this limit to control idea count, output length, or provider spend, because dedicated options govern each of those.
Use a narrower budget option when the concern is specifically turns, tokens, tool edits, or elapsed seconds.
Avoid a single round for contested goals, because one pass leaves no room to repair the first critique.

**Rounds inputs**
The value is one integer between 1 and 3 inclusive.
A single value is supplied per run, and repeated occurrences are not combined into more passes.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than a refinement-pass count for this run.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Rounds**
When it is omitted, the default is 2 passes, which preserves the established refinement behavior.
Command-line values are the only source for this limit, and the run does not read a separate configuration document.
Environment variables do not silently populate this setting, which keeps an invocation reproducible.
An explicit value always takes precedence over the default for exactly one run.
Other settings such as count, categories, and every budget remain independent of the round count.

**Rounds output contract**
Rounds is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective round count travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested rounds without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the stop reason and warnings.
A run that exhausts its rounds with committed edits reports `round_limit` with the final slate.

**How to use Rounds**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the round count shapes refinement rather than defining the task.
Raise the agent-call cap together with rounds, since each extra round costs one critic turn plus one curation turn.
Keep the requested count stable when comparing round settings so slate size does not confound the comparison.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --rounds 2
```

**Examples for Rounds**
A minimal example supplies only the required goal and leaves the round count at its default.
A normal example requests two passes for a goal with moderate uncertainty and enough budget.
An advanced example requests three passes with raised turn and tool caps for a contested slate.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect the stop reason, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --rounds 1
vidbyte-cli --json agents suggest run --goal "{goal}" --rounds 3 --max-agent-calls 128
```

**Related commands for Rounds**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --max-agent-calls when extra rounds need matching model turns to be reachable.
Use --max-tool-calls when extra rounds need matching curation edits to be useful.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Rounds**
A value outside 1 through 3 fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded pass count.
A round whose curation makes no edits ends refinement early with a completed or shortfall reason rather than an error.
A provider or schema failure inside a round is reported as a provider failure and never as a round-limit stop.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Rounds**
This limit itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The round count shapes how many review cycles may spend the caller's provider budget but changes no permission.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the refinement contract.
