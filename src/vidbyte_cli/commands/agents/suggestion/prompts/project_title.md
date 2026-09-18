**Project title**
Project title is the short human-readable name stored with a new local suggestion project.
It is what a person or parent agent reads in project list output to recognize which body of work a key refers to.
The title is also loaded into the context of every project-backed run, so the generator knows which work the recorded feedback belongs to.
It is descriptive metadata only and does not select, authorize, or configure anything by itself.
A title should be recognizable at a glance, such as a product name, a repository name, or the plain name of a long-running goal.
The command keeps the title verbatim apart from trimming surrounding whitespace, so the stored wording is exactly what the caller supplied.

**Purpose of Project title**
The purpose of Project title is to make a project identifiable to readers who never saw the command that created it.
Keys are constrained to lowercase identifiers, while a title can use natural capitalization, spaces, and punctuation that make the scope obvious.
In a suggestion run the title appears as a labelled context line, which helps the generator connect stored reactions to the right work.
In a listing the title sits next to the key, which lets an agent without a transcript choose the correct project instead of creating a duplicate.
A precise title reduces the chance that feedback from one project is mistaken for guidance about another.
It complements the description, which carries scope, by giving that scope a short memorable name.

**When not to use Project title**
Do not use the title to hold instructions to the model, because it is loaded as data and never treated as a directive.
Do not repeat the whole description in the title, since the description field already carries scope and a long title makes listings hard to scan.
Avoid titles that only restate the key in different casing, because they add no information a reader could use.
Do not include credentials, private personal data, or confidential customer details, since the title appears in listings and in run context.
Avoid temporary phrasing such as this week's plan unless the project truly ends when that period ends.
If the right name is still unclear, create the project with a plain working title rather than inventing a misleading one.

**Project title inputs**
The value is one nonempty string of at most 200 characters after surrounding whitespace is trimmed.
Spaces, capital letters, digits, and ordinary punctuation are all accepted inside the title.
A value made only of whitespace is rejected, because an empty title would make the project unrecognizable in listings.
The option is required, so creation refuses to run without a title.
Validation happens in the command's input dataclass together with the key and description, before the catalog is read.
The title is stored as plain text and is never parsed, templated, or reinterpreted as a selector.
Because the title is loaded on every project-backed run, a short title also leaves more of the shared context budget for feedback.

**Defaults and precedence for Project title**
There is no default title, because only the caller knows how the project should be named for its readers.
The value comes only from this option and is never taken from an environment variable, a configuration file, or the key.
Trimming surrounding whitespace is the only normalization applied, so capitalization and internal punctuation are preserved exactly.
The title is fixed at creation in this version, and there is no command that edits it afterwards.
The key, not the title, is what every other command compares, so two projects may share a title without conflict.
Sharing a title is still discouraged because it makes listings ambiguous for a reader choosing between keys.

**Project title output contract**
On success the created document's data includes the title exactly as stored after trimming.
Project list prints the title next to each key in human output and includes it as a field in JSON output.
A project-backed suggestion run includes the title as a context line labelled Project title within the project context kind.
The title is recorded in the result manifest only as part of that context item, with its size and inclusion status.
The title never appears in the file name of the memory document, which is derived from the key alone.
Errors about the title are reported as an invalid project without echoing the rejected value.

**How to use Project title**
Write a short name a teammate would recognize without further explanation.
Pass it in quotes together with the key and description in one project create call.
Prefer the name the work is already known by, such as the repository or product name, over a new invented label.
Keep it under a line so project list output remains easy to scan when several projects exist.
Put detail about scope, boundaries, and goals in the description rather than lengthening the title.
Check the stored title with project list after creation if another agent will rely on it later.
Because the title cannot be edited later in this version, a moment spent choosing a clear name saves confusion for every later reader.

```text
vidbyte-cli agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
```

**Examples for Project title**
A repository example uses a title such as Vidbyte CLI for a project keyed vidbyte-cli.
A goal example uses a title such as Q3 onboarding revamp for a project that spans several components.
A component example uses a title such as Billing API for a project limited to one service.
A weak example uses a title identical to the key, which works but tells a reader nothing new.
JSON output returns the stored title in the created document, which confirms trimming behaved as expected.
If creation fails because of the title, supply a nonempty value within the length bound and retry with the same key.

```text
vidbyte-cli agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
vidbyte-cli --json agents suggest project list
```

**Related commands for Project title**
Use agents suggest project list to read every stored title next to its key.
Use agents suggest run with the project option to load this title into a run's context as part of the project item.
Use the description option of project create to state the project's scope in full sentences.
Use agents suggest feedback accept and reject with the key, not the title, because the key is the selector.
The title and key are always created together and cannot be changed independently in this version.
None of these related commands needs credentials to read the title.
Choosing the right project from its title and description before a feedback call keeps each reaction in the scope it was really about.

**Failure modes for Project title**
A missing title fails as a usage error before any file is read.
A title that is empty after trimming fails as an invalid project and nothing is written.
A title longer than 200 characters fails as an invalid project with the bound named in the error.
A title that is valid never fails on its own content, because its wording is not interpreted.
Creation can still fail for reasons unrelated to the title, such as an existing key or an unwritable data directory.
Recover from a title failure by shortening or filling in the value and repeating the same create call.

**Authentication and permissions for Project title**
Supplying a title requires no Vidbyte login, API key, or provider credential.
The title is stored only in the local project catalog inside the platform-native Vidbyte data directory.
It leaves the machine only when a model-backed run with the project option sends its context to the configured provider.
Dry runs and listings read the title locally and send nothing anywhere.
The title grants no permission to any agent and cannot widen what a generator or critic may do.
Keep sensitive material out of the title because it is shared with the provider whenever the project is used in a real run.
