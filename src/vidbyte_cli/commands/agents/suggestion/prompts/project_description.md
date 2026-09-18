**Project description**
Project description is the plain-language statement of scope stored with a new local suggestion project.
It tells every later project-backed run what body of work the project covers, what it is trying to achieve, and where its boundaries lie.
The description is loaded into the run's context next to the title before any accepted or rejected feedback is read.
That placement matters because a reaction such as rejecting a database suggestion only makes sense once the generator knows what system it was about.
The description may be several sentences long and should read as a briefing a new teammate could act on.
It is stored verbatim apart from trimming surrounding whitespace, and it is never rewritten or summarized by the CLI.

**Purpose of Project description**
The purpose of Project description is to give recorded feedback a frame, so the generator can generalize from past reactions without overgeneralizing.
A clear scope lets the generator tell whether a new idea falls inside the project or drifts into neighbouring work the user never discussed.
It also records durable facts that would otherwise have to be repeated as context flags on every run, such as the product's audience or the repository's role.
For a parent agent that lost its transcript, the description is often the fastest way to confirm it picked the right project from the list.
A description that names what the project is not about is especially useful, because it prevents suggestions from wandering into excluded areas.
Good descriptions make accepted and rejected feedback more informative per record, which means fewer reactions are needed before suggestions improve.

**When not to use Project description**
Do not put run-specific facts in the description, because it is loaded on every run and stale facts will keep influencing suggestions.
Use the constraint, decision, or risk options on a run for information that is true only for that run.
Do not write instructions to the model in the description, since it is loaded as data and never treated as a directive.
Do not paste long documents, transcripts, or file contents, because the description is capped and long text crowds out more useful context.
Keep credentials, personal data, and confidential customer details out of the description because it is sent to the provider on real runs.
If the scope is still unsettled, write what is known today rather than guessing at boundaries that may prove wrong.

**Project description inputs**
The value is one nonempty string of at most 4000 characters after surrounding whitespace is trimmed.
Multiple sentences, line breaks inside a quoted argument, and ordinary punctuation are all accepted.
A value made only of whitespace is rejected, because an empty description would leave feedback without a frame.
The option is required, so creation refuses to run without a description.
Validation happens in the command's input dataclass together with the key and title, before the catalog is read.
The description is stored as plain text and is never parsed, templated, or split into separate records.
Because the description is loaded on every project-backed run, its length also counts against that run's shared context budget.

**Defaults and precedence for Project description**
There is no default description, because only the caller can state the scope of the work.
The value comes only from this option and is never read from an environment variable, a configuration file, or a repository file.
Trimming surrounding whitespace is the only normalization applied, so the rest of the wording is preserved exactly.
The description is fixed at creation in this version, and there is no command that edits it afterwards.
On a project-backed run, caller-supplied context flags come first and the description follows them as part of the project item.
Neither source overrides the other, so a run-level constraint can narrow what the description implies for that single run.

**Project description output contract**
On success the created document's data includes the description exactly as stored after trimming.
Project list prints the description under each key in human output and includes it as a field in JSON output.
A project-backed run includes the description as a context line labelled Project description within the project context kind.
The result manifest records that item's size, hash, and inclusion status, so truncation or omission is visible rather than silent.
The description never appears in file names and never changes where project memory is stored.
Errors about the description are reported as an invalid project without echoing the rejected value.

**How to use Project description**
Write two to five sentences naming the work, its goal, its audience, and anything it deliberately excludes.
Pass it in quotes together with the key and title in one project create call.
Prefer durable facts that will still be true in a month over the details of the current task.
Mention the boundaries that past or expected feedback depends on, such as a rule against adding new infrastructure.
Keep the description well under its limit so it never competes for space with the feedback it frames.
Read it back with project list before relying on it, since it cannot be edited after creation in this version.

```text
vidbyte-cli agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
```

**Examples for Project description**
A repository example describes a command-line client, its users, and the rule that research runs on the backend rather than locally.
A goal example describes a quarter-long onboarding effort, the metric it targets, and the teams it must not disrupt.
A component example describes one service, the interfaces it owns, and the neighbouring services that are out of scope.
A weak example is a single phrase that repeats the title, which gives feedback almost no frame to be interpreted in.
JSON output returns the stored description in the created document, which lets an agent verify the exact wording.
If creation fails because of the description, shorten or fill in the value and retry with the same key and title.

```text
vidbyte-cli agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
vidbyte-cli --json agents suggest project list
```

**Related commands for Project description**
Use agents suggest project list to read every stored description next to its key and title.
Use agents suggest run with the project option to load this description into a run as part of the project context item.
Use run-level context options such as constraint and decision for facts that apply only to one run.
Use agents suggest feedback accept and reject to add reactions that the description will frame on later runs.
Use dry-run on a project-backed run to see the description's manifest entry without calling a provider.
None of these commands edits the description, which is set once by project create.

**Failure modes for Project description**
A missing description fails as a usage error before any file is read.
A description that is empty after trimming fails as an invalid project and nothing is written.
A description longer than 4000 characters fails as an invalid project with the bound named in the error.
A valid description never fails on its content, because its wording is not interpreted by the CLI.
Creation can still fail for unrelated reasons, such as an existing key or an unwritable data directory.
Recover from a description failure by shortening or supplying the value and repeating the same create call.
A failed call writes nothing, so repeating it after a correction cannot leave a half-created project behind.

**Authentication and permissions for Project description**
Supplying a description requires no Vidbyte login, API key, or provider credential.
The description is stored only in the local project catalog inside the platform-native Vidbyte data directory.
It leaves the machine only when a model-backed run with the project option sends its context to the configured provider.
Dry runs and listings read the description locally and send nothing anywhere.
The description grants no permission to any agent and cannot widen what a generator or critic may do.
Keep sensitive material out of the description because it is shared with the provider whenever the project is used in a real run.
