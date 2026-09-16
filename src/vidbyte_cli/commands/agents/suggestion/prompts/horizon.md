**Horizon**
Horizon describes when a suggestion should become useful: immediately, next in sequence, later, or without a temporal restriction.
An unrestricted horizon supports a deliberate mix across time for goals with no dominant urgency.
A narrower horizon helps when timing matters more than broad opportunity discovery.
Each returned idea still records its concrete horizon so the caller can inspect the resulting mix.
Temporal focus changes selection after review rather than changing the underlying goal.

**Purpose of Horizon**
The purpose of Horizon is to tell the workflow which time frame the caller cares about most.
That focus filters the validated slate to ideas whose horizon matches, keeping timing aligned with intent.
It also lets the critic judge feasibility against the right window instead of an assumed one.
The filter works alongside category selection and count rather than replacing either.
When set to `any`, every horizon passes through and the slate mixes immediate, next, and later moves.

**When not to use Horizon**
Do not set Horizon merely because the option exists when timing truly does not matter for the goal.
Omit it when the caller wants a deliberate mix and let the unrestricted default apply.
Do not use this filter to control idea count or refinement depth, because dedicated options govern each of those.
Use a narrower setting when the concern is specifically selection breadth, budgets, or reasoning lenses.
Avoid the immediate horizon for goals whose payoff is structurally long-term, because the filter will hide the best moves.

**Horizon inputs**
The value is one of `now`, `next`, `later`, or `any`.
A single value is supplied per run, and repeated occurrences are not combined.
Shell quoting does not change the meaning, while any other string is rejected before provider work.
The command does not reinterpret the value as anything other than a timing filter for this run.
Unsupported values fail fast at the request boundary with a typed input error.

**Defaults and precedence for Horizon**
When it is omitted, the default is `any`, which preserves the mixed-timing slate behavior.
Command-line values are the only source for this filter, and the run does not read a separate configuration document.
Environment variables do not silently populate this setting, which keeps an invocation reproducible.
An explicit value always takes precedence over the default for exactly one run.
Other settings such as count, categories, rounds, and every budget remain independent of the horizon.

**Horizon output contract**
Horizon is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective horizon travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested horizon without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve per-idea horizons and coverage.
A filtered slate may be smaller than requested, and the shortfall warning explains the selectivity.

**How to use Horizon**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual horizon while preserving shell quoting.
Combine the option with a precise goal because the horizon filters timing rather than defining the task.
Match the horizon to the decision at hand instead of defaulting to immediate for every goal.
Keep the horizon stable when comparing categories so timing does not confound the comparison.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --horizon next
```

**Examples for Horizon**
A minimal example supplies only the required goal and leaves timing unrestricted.
A normal example narrows to next actions for a goal with a clear immediate sequence.
An advanced example requests later moves with JSON output for long-range planning by another agent.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect per-idea horizons and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --horizon now
vidbyte-cli --json agents suggest run --goal "{goal}" --horizon later --count 8
```

**Related commands for Horizon**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --count when the slate itself should be larger or smaller rather than differently timed.
Use --category when the slate should draw on specific opportunity types rather than the whole registry.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Horizon**
An unsupported horizon string fails before the provider is loaded because the request dataclass requires a known value.
A filter that removes every idea yields an empty validated slate with a shortfall reason, not an error.
A provider or schema failure is reported as a provider failure and is never converted into a false empty result.
Budget and validation failures keep their own typed paths and are never relabeled as horizon problems.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Horizon**
This filter itself does not grant access to files, providers, accounts, repositories, or execution tools.
The four values validate locally without credentials, while model-backed runs still require the configured provider.
The horizon shapes which validated ideas reach the caller but changes no permission.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the timing contract.
