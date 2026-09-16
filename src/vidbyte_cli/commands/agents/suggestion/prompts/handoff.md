**Handoff**
Handoff extracts one reviewed idea from a saved suggestion result into a deterministic action packet.
It is a local read operation for callers that want to pass one selected idea to a person or another agent.
The command requires both a result path and the exact stable idea identifier.
It validates the saved envelope before selecting the idea and never accepts a title or prefix as a substitute.
No provider, credential, or execution permission is needed for extraction.

**Purpose of Handoff**
The purpose of Handoff is to move one evaluated idea from suggestion output into execution input.
That packet centers ordered actions, decisions along the way, material considerations, and completion checks.
It also embeds the bounded cited evidence behind the idea, so the executor can judge without reopening the run.
The handoff works alongside the saved result rather than replacing it.
The packet itself never grants authority; it only proposes the next move with its support.

**When not to use Handoff**
Do not use Handoff when no run has produced a result document yet, because there is nothing to extract.
Omit it when the caller needs the whole slate rather than one selected idea.
Do not use this command to rerun reasoning, because extraction never invokes a model.
Use a fresh run when the goal or context changed since the saved result was produced.
Avoid extracting by title or rank, because only the stable identifier addresses an idea deterministically.

**Handoff inputs**
The command takes a result file path and one exact idea identifier such as `idea-003`.
The path must name a readable saved envelope from a previous run.
The identifier must match one idea in that envelope exactly, with no fuzzy matching.
Whitespace around values is trimmed, while blank or malformed values are rejected before any read.
Unknown paths and identifiers fail fast with typed errors that name the offending value.

**Defaults and precedence for Handoff**
There is no useful default result path, because extraction must name the document to read.
There is no default idea either, since the caller must choose which reviewed option to carry forward.
Command-line values are the only source for both inputs, and the command reads no separate configuration.
Environment variables do not supply the path or identifier, which keeps extraction reproducible.
Both values apply to exactly one extraction and carry no state into later commands.

**Handoff output contract**
Handoff reserves stdout for results only, while diagnostics travel on the error channel.
Human output prints the copyable execution prompt for the selected idea.
JSON and JSONL output preserve the full handoff fields with embedded evidence and stop conditions.
The packet carries an explicit not-granted authority marker so it can never be mistaken for permission.
Errors arrive as typed machine envelopes with a repair-oriented description and no secret echo.

**How to use Handoff**
Use the command below as the smallest valid invocation shape for this command.
Replace each brace-delimited placeholder with the caller's actual path and identifier while preserving shell quoting.
Run the suggestion workflow first so a saved result document exists to read.
Select the identifier from the saved ideas rather than guessing it from titles.
Keep the saved document alongside the handoff so the executor can verify provenance when needed.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest handoff --input "{result-path}" --idea idea-003
```

**Examples for Handoff**
A minimal example extracts one idea from a saved result for a person to read.
A normal example emits JSON so another agent can execute the packet programmatically.
An advanced example pairs extraction with the saved manifest to audit evidence before acting.
Piping is appropriate only for a caller that captures the emitted packet document.
JSON output is the stable choice when another agent will execute the suggested actions.
If an example fails, preserve the same path and correct the identifier before changing anything else.

```text
vidbyte-cli agents suggest handoff --input ./result.json --idea idea-001
vidbyte-cli --json agents suggest handoff --input ./result.json --idea idea-003
```

**Related commands for Handoff**
Use agents suggest run first to produce the result document this command reads.
Use agents suggest categories --view-all when the original run needs better lenses before rerunning.
Use dry-run when a planned run's shape needs inspection without credentials or model usage.
Use the saved manifest and warnings to understand what the extracted idea survived.
Use the execution prompt as the executor's briefing rather than re-deriving actions from the slate.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Handoff**
A missing result path fails before any read because extraction requires a named document.
An unknown identifier fails as a typed selection error instead of guessing the nearest title.
A malformed or foreign envelope fails validation rather than producing a plausible-looking packet.
No provider failure is possible here, because extraction never contacts a provider.
Recover by correcting the saved path or identifier and rerunning the same request.

**Authentication and permissions for Handoff**
This read requires no credentials, because it never contacts a provider.
It reads only the result path explicitly named by the caller and scans nothing else.
Extraction grants no authority: the packet's authority marker stays not-granted by construction.
The executor must obtain its own permissions before acting on the suggested actions.
Permission questions belong to the execution environment, not to this read.
