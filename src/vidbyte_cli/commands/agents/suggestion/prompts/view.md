**View**
View expands a single category into its full high-level definition for one identifier.
Pass the exact category identifier shown by the all-categories view.
The result includes the authored description and the considerations that guide suggestions of that type.
The command reads packaged content locally and makes no model call.
An unknown identifier is rejected before any output is produced.

**Purpose of View**
The purpose of View is to explain one reasoning lens deeply enough to select it well.
That depth helps callers distinguish nearby categories whose summaries sound alike.
It also shows the considerations the generator and critic will apply under that lens.
The view works alongside the registry summary rather than replacing it.
Agents use the expanded definition to decide whether the lens fits the goal before spending a run.

**When not to use View**
Do not open the expanded view when the summary list already distinguishes the lenses clearly.
Omit it for routine runs with a stable selection that rarely needs re-examination.
Do not use this read to start reasoning, because inspection never invokes a model.
Use the summary view when the need is breadth across lenses rather than depth in one.
Avoid reading every definition when one or two candidate lenses are already in mind.

**View inputs**
The view takes one exact category identifier as its selection.
The identifier must match the registry spelling shown by the summary view.
Whitespace around the value is trimmed, while a blank value is rejected before any read.
No goal, context, file, or budget is required or accepted for inspection.
Unknown identifiers fail fast with a typed error that names the offending value.

**Defaults and precedence for View**
There is no default identifier, because the caller must name the lens to expand.
Command-line values are the only source for the selection, and the view reads no separate configuration.
Environment variables do not supply the identifier, which keeps inspection reproducible.
The value applies to exactly one read and carries no state into later commands.
Selection for a later run remains an independent choice made with --category.

**View output contract**
View reserves stdout for results only, while diagnostics travel on the error channel.
Human output prints the full definition with its considerations for careful reading.
JSON and JSONL output emit the versioned envelope with the identifier, description, and considerations.
The expanded definition is informative guidance, not an instruction to execute work.
Errors arrive as typed machine envelopes with a repair-oriented description and no secret echo.

**How to use View**
Use the command below as the smallest valid invocation shape for this view.
Replace the brace-delimited placeholder with the caller's actual identifier while preserving shell quoting.
Read the summary list first when unsure which identifier names the intended lens.
Carry the chosen identifier into a later run with a --category option.
Keep the installed CLI current so the viewed definition matches the one validation enforces.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest categories --view verification
```

**Examples for View**
A minimal example expands one familiar lens to confirm its boundary before selecting it.
A normal example compares two nearby lenses by reading each definition in turn.
An advanced example emits JSON so another agent can weigh the considerations programmatically.
Piping is appropriate only for a caller that captures the emitted definition document.
JSON output is the stable choice when another agent will select lenses for a later run.
If an example fails, check the identifier spelling against the summary list before changing anything else.

```text
vidbyte-cli agents suggest categories --view verification
vidbyte-cli --json agents suggest categories --view experiment
```

**Related commands for View**
Use agents suggest categories --view-all when breadth across lenses matters more than depth in one.
Use agents suggest run with the chosen identifier passed as --category.
Use --all-categories when the run should consider the whole registry instead of one lens.
Use dry-run when a planned run's shape needs inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for View**
An unknown identifier fails locally with a typed error before any output is produced.
A damaged installation with missing definition assets fails as a local error rather than a terse stub.
No provider failure is possible here, because inspection never contacts a provider.
Version skew between the viewed definition and a stale install resolves by reinstalling the CLI.
Recover by correcting the identifier spelling against the summary list and rerunning the same read.

**Authentication and permissions for View**
This read requires no credentials, because it never contacts a provider.
It reads only packaged assets bundled with the installed CLI and scans nothing else.
Inspection grants no access to files, accounts, repositories, or execution tools.
The definition is informative guidance, not an instruction to execute work.
Permission questions do not arise for a pure local read.
