**Extra Compute**
Extra Compute runs one independent suggestion agent for each selected category and combines their structured results before critique.
Each category receives the same goal and caller context, but its own focused category window, so the run can explore more distinct directions.
The default is off because one shared window is usually enough and uses fewer model turns.
Enable it when breadth matters more than latency or when several categories deserve separate attention.
The combined pool is still bounded by the requested count and the workflow's budgets.

**Purpose of Extra Compute**
The purpose of Extra Compute is to widen generation across categories without widening any single context window.
That fan-out gives each category a dedicated generator turn with undiluted category signal.
It also preserves comparability, because every per-category result is labeled before combination.
The topology works alongside the independent critic, which still reviews the combined candidates as one slate.
A provider failure in any branch stops the provider-backed run with its typed error rather than a partial pool.

**When not to use Extra Compute**
Do not enable Extra Compute merely because more agents sound better when one shared window already converges.
Omit it when latency or turn budget matters more than directional breadth.
Do not use this flag to raise the idea count, because the requested count still bounds the final slate.
Use a narrower change when the need is specifically more rounds, larger budgets, or different categories.
Avoid the fan-out for single-category runs, because one branch duplicates the normal generation path.

**Extra Compute inputs**
The value is a boolean flag that takes no argument.
Presence enables per-category fan-out, while absence uses one shared generation window.
The flag combines freely with every other option, and category selection decides how many branches run.
Shell quoting does not apply, while an unexpected flag value is rejected before any work.
The command treats the flag as a topology switch for exactly one invocation.

**Defaults and precedence for Extra Compute**
When it is omitted, the default is off and generation runs once in the shared window.
Command-line presence is the only source for this topology, and the run does not read a separate configuration document.
Environment variables do not silently enable the fan-out, which keeps an invocation reproducible.
An explicit flag always takes precedence over the default for exactly one run.
The agent-call, token, and time budgets should be raised together with the flag since branches multiply turns.

**Extra Compute output contract**
Extra Compute is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the enabled topology travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested topology without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the settings and usage.
Per-branch spend appears in the aggregate usage mapping rather than as separate per-category accounts.

**How to use Extra Compute**
Use the command below as the smallest valid invocation shape for this flag.
Combine the flag with explicit categories so each branch has a distinct reasoning lens.
Raise the agent-call and token budgets together with the flag to cover the multiplied turns.
Keep the requested count stable so broader generation does not inflate the final slate.
Inspect usage after the run to learn the real per-branch cost before enabling it routinely.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --category verification --category experiment --extra-compute
```

**Examples for Extra Compute**
A minimal example supplies only the required goal and leaves generation in its shared window.
A normal example fans out across two categories with raised turn and token budgets.
An advanced example combines the fan-out with three rounds and JSON output for another agent.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect usage, settings, and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --extra-compute
vidbyte-cli --json agents suggest run --goal "{goal}" --category verification --category experiment --extra-compute --max-agent-calls 128
```

**Related commands for Extra Compute**
Use agents suggest categories --view-all when the caller needs to choose the fan-out lenses before running.
Use --max-agent-calls when the multiplied branches need matching model turns to complete.
Use --max-total-tokens when the multiplied branches need matching token allowance.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Extra Compute**
A branch provider failure stops the run with its typed error rather than a silently partial pool.
An empty combined pool yields a shortfall result, not filler ideas.
A provider or schema failure is reported as a provider failure and is never converted into a false no-suggestions result.
Budget exhaustion across branches keeps the normal limit stop reasons with the committed snapshot.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Extra Compute**
This topology itself does not grant access to files, providers, accounts, repositories, or execution tools.
The flag validates locally without credentials, while model-backed runs still require the configured provider.
Each branch spends the caller's provider budget under the same read-only deny-all agent settings.
Branch contexts carry only the caller-supplied records and the focused category window.
Permission failures should be repaired at the provider boundary rather than by weakening the topology contract.
