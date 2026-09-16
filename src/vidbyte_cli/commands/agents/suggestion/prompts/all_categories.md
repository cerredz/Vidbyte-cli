**All Categories**
All Categories makes whole-registry consideration an explicit part of the suggestion request.
It invites every documented opportunity type without demanding one result from each type.
This is already the natural behavior when no narrower category set is supplied.
Making the intent explicit helps agents preserve breadth in durable request records.
The result limit and relevance threshold still govern the final slate independently.

**Purpose of All Categories**
The purpose of All Categories is to record that the caller deliberately wants unbounded reasoning lenses.
That record prevents a later reader from mistaking an empty selection for an oversight.
It also keeps the request self-describing, because the flag states breadth where silence would be ambiguous.
The flag works alongside horizon and count rather than replacing either.
Selection validation accepts the flag only when no explicit categories are also given.

**When not to use All Categories**
Do not set All Categories merely because the flag exists when a focused lens would serve the goal better.
Omit it when the caller wants the registry default silently, without recording the intent.
Do not use this flag together with explicit categories, because the combination is contradictory and rejected.
Use narrower --category values when the goal benefits from one or two specific reasoning lenses.
Avoid whole-registry breadth for goals with a clear single-lens answer, because breadth dilutes the slate.

**All Categories inputs**
The value is a boolean flag that takes no argument.
Presence requests the whole registry, while absence leaves selection to the category options or the default.
The flag combines with every option except explicit category selections.
Shell quoting does not apply, while an unexpected flag value is rejected before any work.
Combining the flag with any --category value fails fast as a typed input error.

**Defaults and precedence for All Categories**
When it is omitted and no categories are given, the run still considers the whole registry by default.
Command-line presence is the only source for the explicit flag, and the run does not read a separate configuration document.
Environment variables do not silently enable whole-registry mode, which keeps an invocation reproducible.
An explicit flag always takes precedence as a recorded intent for exactly one run.
Categories and the flag are mutually exclusive, and the validator enforces exactly one selection style.

**All Categories output contract**
All Categories is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the recorded selection travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the whole-registry intent without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve category coverage.
Coverage reporting shows which lenses the final ideas actually drew on.

**How to use All Categories**
Use the command below as the smallest valid invocation shape for this flag.
Combine the flag with a precise goal because breadth selects lenses rather than defining the task.
Leave --category out entirely whenever this flag is present.
Narrow with horizon or count when the broad slate needs shaping without losing lenses.
Keep the selection stable when comparing budgets so lens breadth does not confound the comparison.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --all-categories
```

**Examples for All Categories**
A minimal example supplies only the required goal and leaves selection at its silent default.
A normal example records whole-registry intent explicitly for an exploratory goal.
An advanced example combines the flag with a horizon filter and JSON output for another agent.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect coverage, settings, and handoffs.
If an example fails, preserve the same goal and correct the named selection before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --all-categories
vidbyte-cli --json agents suggest run --goal "{goal}" --all-categories --horizon any --count 10
```

**Related commands for All Categories**
Use agents suggest categories --view-all when the caller wants to read the registry before choosing breadth.
Use --category when the slate should draw on specific opportunity types instead.
Use --horizon when the slate should favor a particular time frame within the broad lenses.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for All Categories**
Combining the flag with explicit categories fails before the provider is loaded as a contradictory selection.
An empty registry, which cannot happen in practice, would fail as a configuration error rather than an empty slate.
A provider or schema failure is reported as a provider failure and is never converted into a false selection error.
Budget and validation failures keep their own typed paths and are never relabeled as category problems.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for All Categories**
This flag itself does not grant access to files, providers, accounts, repositories, or execution tools.
The boolean validates locally without credentials, while model-backed runs still require the configured provider.
Whole-registry breadth changes which lenses the model may use but changes no permission.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the selection contract.
