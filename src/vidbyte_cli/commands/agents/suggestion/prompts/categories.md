**Categories**
Categories presents every recognized type of next-action suggestion in one registry view.
Each entry names a distinct opportunity pattern and explains the role it plays in advancing a goal.
The same versioned registry governs agent visibility, caller selection, prompt context, and result validation.
This shared source prevents displayed categories from drifting away from what generation can actually use.
Registry inspection requires no model reasoning and no credentials of any kind.

**Purpose of Categories**
The purpose of Categories is to let callers and agents read the full taxonomy before choosing lenses.
That reading supports informed selection instead of guessing identifiers from memory.
It also keeps documentation, validation, and prompt context anchored to one versioned source.
The view works alongside the expanded single-category view rather than replacing it.
Machine-readable output lets another agent examine the complete taxonomy programmatically.

**When not to use Categories**
Do not open the registry view when the caller already knows the exact lenses the goal needs.
Omit it for routine runs with a stable category selection that rarely changes.
Do not use this read to start reasoning, because inspection never invokes a model.
Use the expanded view when a short summary is not enough to distinguish nearby categories.
Avoid re-reading the registry on every run when a cached copy is fresh, since the taxonomy changes rarely.

**Categories inputs**
The view takes no selection input beyond its display flags.
It reads the packaged registry bundled with the installed CLI.
No goal, context, file, or budget is required or accepted for inspection.
Shell quoting does not apply to a pure read.
The command treats the registry as local data and never contacts a provider.

**Defaults and precedence for Categories**
The view always shows the complete registry; there is no narrower default to configure.
No command-line value changes which entries appear, only how they are rendered.
Environment variables do not alter the registry contents, which keeps inspection reproducible.
Human and machine renderings draw on the same definitions for exactly one installed version.
Selection for a later run remains an independent choice made with --category or --all-categories.

**Categories output contract**
Categories reserves stdout for results only, while diagnostics travel on the error channel.
Human output prints the high-level summary of every category for quick scanning.
JSON and JSONL output emit the versioned envelope with identifiers, titles, and descriptions.
The summaries describe opportunity types conceptually and omit provider and implementation mechanics.
Errors arrive as typed machine envelopes with a repair-oriented description and no secret echo.

**How to use Categories**
Use the command below as the smallest valid invocation shape for this view.
Choose the human or JSON rendering based on whether a person or another agent consumes the taxonomy.
Pass a chosen identifier to the expanded view when one summary needs its full definition.
Carry selected identifiers into a later run with repeated --category options.
Keep the installed CLI current so the viewed registry matches the one validation enforces.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest categories --view-all
```

**Examples for Categories**
A minimal example prints the full summary list for a person choosing lenses.
A normal example emits JSON so another agent can filter identifiers programmatically.
An advanced example chains inspection into a run by feeding chosen identifiers to --category.
Piping is appropriate only for a caller that captures the emitted result document.
JSON output is the stable choice when another agent will select categories for a later run.
If an example fails, check the installed version and subcommand spelling before changing anything else.

```text
vidbyte-cli agents suggest categories --view-all
vidbyte-cli --json agents suggest categories --view-all
```

**Related commands for Categories**
Use agents suggest categories --view {category-id} when one category needs its full definition.
Use agents suggest run with --category values chosen from this registry.
Use --all-categories when the run should consider the whole registry explicitly.
Use dry-run when a planned run's shape needs inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Categories**
An unknown subcommand or flag fails locally with a usage error before any output.
A damaged installation with missing registry assets fails as a local error rather than an empty list.
No provider failure is possible here, because inspection never contacts a provider.
Version skew between the viewed registry and a stale install resolves by reinstalling the CLI.
Recover by correcting the subcommand spelling and rerunning the same read.

**Authentication and permissions for Categories**
This read requires no credentials, because it never contacts a provider.
It reads only packaged assets bundled with the installed CLI and scans nothing else.
Inspection grants no access to files, accounts, repositories, or execution tools.
The taxonomy is informative guidance, not an instruction to execute work.
Permission questions do not arise for a pure local read.
