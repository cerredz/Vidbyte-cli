**Category**
Category identifies the kind of opportunity a suggestion represents for one run.
Several categories can be selected together when the goal benefits from more than one reasoning lens.
Unknown identifiers are rejected before generation because silent broadening would change caller intent.
A missing selection lets the agent consider the complete registry instead.
Category choice constrains candidate types without requiring equal representation across them.

**Purpose of Category**
The purpose of Category is to focus generation and critique on the opportunity patterns that fit the goal.
That focus gives the generator a sharper brief and the critic a clearer standard for relevance.
It also makes the final mix inspectable, because the result reports actual coverage per lens.
Selection works alongside count and horizon rather than replacing either.
Repeated options combine into one explicit lens set for exactly one run.

**When not to use Category**
Do not select categories merely because the option exists when the goal genuinely spans the registry.
Omit selection when whole-registry breadth is intended, optionally recording it with --all-categories.
Do not use this option to browse definitions, because the category views answer that without a model.
Use --all-categories when explicit breadth matters more than listing every lens by name.
Avoid over-narrowing to a single lens for exploratory goals, because the slate will miss adjacent opportunities.

**Category inputs**
The value is one known category identifier per repeated option occurrence.
Each identifier must match the versioned registry exactly, including spelling and separators.
Whitespace around a value is trimmed at the request boundary, while an empty value is rejected before provider work.
Duplicate identifiers are rejected rather than counted twice.
Unknown identifiers fail fast at the request boundary with a typed input error.

**Defaults and precedence for Category**
When no category is given and --all-categories is absent, the run still considers the whole registry.
Command-line values are the only source for selection, and the run does not read a separate configuration document.
Environment variables do not silently populate the lens set, which keeps an invocation reproducible.
Explicit selections always take precedence over the silent default for exactly one run.
Combining explicit categories with --all-categories is contradictory and rejected by validation.

**Category output contract**
Category is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the selected lenses travel inside the validated settings and the category coverage.
For dry-run output, the manifest records the requested selection without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve coverage per lens.
The final result reports actual coverage so the caller can inspect the resulting mix.

**How to use Category**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual identifier while preserving shell quoting.
Repeat the option when more than one independent lens should apply to the same goal.
Combine selection with a precise goal because lenses focus reasoning rather than defining the task.
Read the registry views first when unsure which identifiers fit the decision at hand.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --category verification
```

**Examples for Category**
A minimal example supplies only the required goal and leaves selection at the registry default.
A normal example focuses one lens on a goal with a clear verification need.
An advanced example combines two lenses with JSON output for another agent to consume.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect coverage, settings, and handoffs.
If an example fails, preserve the same goal and correct the named identifier before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --category verification
vidbyte-cli --json agents suggest run --goal "{goal}" --category verification --category experiment
```

**Related commands for Category**
Use agents suggest categories --view-all when the caller needs to read the registry before selecting.
Use agents suggest categories --view {category-id} when one lens needs its full definition.
Use --all-categories when the run should consider the whole registry explicitly.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Category**
An unknown identifier fails before the provider is loaded because silent broadening would change caller intent.
A duplicate identifier fails as invalid input instead of double-counting the lens.
Combining categories with --all-categories fails as a contradictory selection.
A provider or schema failure is reported as a provider failure and is never converted into a false selection error.
Recover by correcting the specific identifier named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Category**
This selection itself does not grant access to files, providers, accounts, repositories, or execution tools.
Identifiers validate locally without credentials, while model-backed runs still require the configured provider.
Selection changes which lenses the model may use but changes no permission.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the selection contract.
