**Count**
Count is the maximum number of worthwhile ideas the final slate may contain.
Five balances useful breadth with the attention required to compare candidates.
Values from 2 through 15 support narrow decisions and broader exploration alike.
The generator considers a larger bounded pool before critique selects the strongest subset.
The count is never a quota that justifies weak filler ideas.

**Purpose of Count**
The purpose of Count is to tell the workflow how large a useful slate looks for this goal.
That target sizes the generation pool, because the pool is computed as a multiple of the requested count.
It also bounds the final ranking, so the caller receives at most the requested number of ideas.
The count works alongside category selection and horizon filtering rather than replacing either.
When fewer worthwhile ideas survive review, the result reports a shortfall instead of padding the slate.

**When not to use Count**
Do not raise Count merely because a larger slate sounds better when five already covers the decision.
Omit it when the caller has no size requirement and let the default of five apply.
Do not use this value to control refinement passes, output length, or provider spend, because dedicated options govern each of those.
Use a narrower setting when the concern is specifically rounds, tokens, turns, or elapsed seconds.
Avoid the maximum for simple goals, because a wide slate of thin ideas helps less than a few grounded ones.

**Count inputs**
The value is one integer between 2 and 15 inclusive.
A single value is supplied per run, and repeated occurrences are not combined into a larger slate.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than a maximum slate size for this run.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Count**
When it is omitted, the default is 5 ideas, which preserves the established slate size.
Command-line values are the only source for this target, and the run does not read a separate configuration document.
Environment variables do not silently populate this setting, which keeps an invocation reproducible.
An explicit value always takes precedence over the default for exactly one run.
Other settings such as rounds, categories, horizon, and every budget remain independent of the count.

**Count output contract**
Count is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the requested and returned counts travel inside the result envelope beside the ideas.
For dry-run output, the manifest records the requested count without spending any provider turn.
Human output prints the returned-over-requested counts in the header, while JSON and JSONL output preserve the exact numbers.
A smaller result includes an explicit shortfall warning so selectivity cannot resemble failure.

**How to use Count**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the count sizes the slate rather than defining the task.
Keep the count stable when comparing categories or rounds so slate size does not confound the comparison.
Raise generation headroom through extra compute instead of inflating the count when breadth is the real need.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --count 5
```

**Examples for Count**
A minimal example supplies only the required goal and leaves the count at its default.
A normal example requests a focused pair of ideas for a narrow near-term decision.
An advanced example requests a wide slate with several categories for broad exploration.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect identifiers, manifests, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --count 2
vidbyte-cli --json agents suggest run --goal "{goal}" --count 10 --category verification --category experiment
```

**Related commands for Count**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --category when the slate should draw on specific opportunity types rather than the whole registry.
Use --horizon when the slate should favor a particular time frame rather than any timing.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Count**
A value outside 2 through 15 fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded slate size.
A shortfall result is not an error: it means review rejected filler and kept only worthwhile ideas.
A provider or schema failure is reported as a provider failure and is never converted into a false shortfall.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Count**
This target itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The count shapes how many ideas the caller's provider budget may produce but changes no permission.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the slate contract.
