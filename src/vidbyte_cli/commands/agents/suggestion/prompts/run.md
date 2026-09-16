**Run**
Run develops concrete next actions for one meaningful goal through generation, independent critique, and tool-enabled curation.
It returns only ideas that can be explained, evaluated, and handed to another agent for execution.
Supplied context shapes what counts as relevant, feasible, novel, and timely for the caller's situation.
A broader internal candidate pool gives independent critique enough material to reject weak or redundant directions.
The final slate may be smaller than requested when stronger ideas are exhausted, and every survivor carries evidence and an execution-ready action structure.

**Purpose of Run**
The purpose of Run is to turn caller context into a ranked slate of next actions without executing anything.
That slate lets a parent agent choose a move with cited evidence instead of guessing from raw notes.
It also records exactly what was considered, what was rejected, and what is missing, so the decision stays auditable.
The command never performs the suggested work itself; it only produces the evaluated options.
Every run emits a versioned result envelope that machines can parse and humans can scan.

**When not to use Run**
Do not use Run when the caller needs execution, research threads, or artifact bodies, because this command only suggests.
Omit it when there is no goal worth advancing and no context worth reviewing.
Do not use this command to browse the category taxonomy, because the categories views answer that without a model.
Use a narrower read command when the need is a single category definition or a saved handoff packet.
Avoid launching repeated runs with identical inputs when the first slate already answers the goal.

**Run inputs**
The run accepts one required goal plus optional context records, files, categories, and budgets.
Context arrives as repeated text options or named file paths, and every record keeps its source and semantic identity.
Selection options narrow the reasoning lenses, while budget options bound turns, tokens, edits, rounds, and time.
The request dataclass validates every value before any provider work begins.
Invalid, empty, oversized, or unknown values fail fast with typed errors rather than puzzling model output.

**Defaults and precedence for Run**
When options are omitted, the run uses five ideas, the full category registry, two refinement rounds, and the default budgets.
Command-line values are the only source for the request, and the run does not read a separate configuration document.
Environment variables do not silently populate the request, which keeps an invocation reproducible.
Explicit caller input always takes precedence over defaults for exactly one run.
The result manifest records what was supplied and whether each bounded value was included, truncated, or omitted.

**Run output contract**
Run reserves stdout for results only, while progress, warnings, and diagnostics travel on the error channel.
Human output prints a ranked list with categories and first actions for quick scanning.
JSON and JSONL output emit the versioned envelope with settings, manifest, ideas, coverage, warnings, usage, and stop reason.
A dry run emits the same envelope shape with no ideas and a dry-run stop reason.
Errors arrive as typed machine envelopes with a repair-oriented description and no secret echo.

**How to use Run**
Use the command below as the smallest valid invocation shape for this command.
Replace each brace-delimited placeholder with the caller's actual text while preserving shell quoting around spaces.
Repeat context options when more than one independent record should be supplied.
Combine the goal with categories and budgets only when they answer a real selection or resource question.
Add files explicitly by path when evidence lives outside the command line.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}"
```

**Examples for Run**
A minimal example supplies only the required goal and accepts every default for selection and budgets.
A normal example adds focused context records and two categories that match the decision at hand.
An advanced example enables extra compute, raises the budgets, and emits JSON for another agent to consume.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect identifiers, manifests, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named input or path before changing the reasoning settings.

```text
vidbyte-cli agents suggest run --goal "{goal}" --category verification
vidbyte-cli --json agents suggest run --goal "{goal}" --trajectory "{value}" --count 8 --rounds 3
```

**Related commands for Run**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use agents suggest categories --view {category-id} when one category needs a fuller conceptual definition.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
Use the context options when the signal is more accurately a decision, constraint, risk, or current commitment.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Run**
A missing goal fails before the provider is loaded because the request dataclass requires a meaningful boundary.
An invalid option value fails as typed input error instead of becoming a misleading silent default.
An oversized context value is truncated only within the documented bound and the result records that status as a warning.
A provider or schema failure is reported as a provider failure and is never converted into a false no-suggestions result.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Run**
This command reads only the context the caller supplies and never scans a workspace or agent history.
Text values and budgets validate locally without credentials, while model-backed runs require the configured provider.
The --files option reads only paths explicitly named by the caller.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Provider credentials are used only when a real model-backed run is requested and are never copied into result prose.
Permission failures should be repaired at the provider or filesystem boundary rather than by weakening the request contract.
