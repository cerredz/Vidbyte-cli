**Project key**
Project key is the unique identifier this command registers for a new local suggestion project.
It is the one value every later command uses to address the project, including feedback accept, feedback reject, and a suggestion run with the project option.
The key also names the project's memory file on disk, which is why its character set is deliberately narrow.
Choose it once and keep it stable, because a project cannot be renamed and a new key starts an empty feedback history.
A good key is short and names the body of work, such as a repository, product area, or long-running goal, rather than a single run.
The command stores the key exactly as validated, so the value a caller passes later must match it character for character.

**Purpose of Project key**
The purpose of Project key is to give a parent agent a stable handle it can store, pass between sessions, and paste into later commands without ambiguity.
Titles and descriptions are free prose that may change in meaning or wording, while the key is the exact selector the catalog compares.
Keeping identity separate from description lets the title read naturally for a person while the key stays safe for scripts and file names.
The key is what makes feedback cumulative, because every reaction recorded under the same key lands in the same ordered history.
A predictable key also lets an agent that lost its transcript recover the project from project list instead of creating a duplicate.
That recovery is only reliable when the key names the work plainly enough for an agent to recognize it later.

**When not to use Project key**
Do not register a new key for work that already has a project, because feedback split across two keys is never merged and each run sees only half of it.
Do not encode dates, run numbers, or session identifiers in the key unless the project truly is scoped to that period.
Avoid keys that describe a single suggestion or idea, since a project is meant to collect many reactions over time.
Do not place private data, credentials, or customer names in the key, because it appears in listings, result documents, and file names.
Do not rely on case or punctuation to distinguish two projects, since uppercase letters and punctuation other than hyphens and underscores are rejected.
If you are unsure whether a suitable project exists, run project list before creating anything new.

**Project key inputs**
The value is one string of 1 to 64 characters drawn from lowercase letters, numbers, hyphens, and underscores.
The first character must be a lowercase letter or a number, so a key cannot begin with a hyphen or an underscore.
Whitespace around the value is trimmed before validation, and whitespace inside the key is rejected.
Slashes, dots, and other path characters are rejected outright, which keeps the key from ever naming a location outside the project directory.
The option is required, so the command refuses to run without it before reading any file.
Validation happens in the command's input dataclass, before the catalog is opened, so an invalid key never touches disk.

**Defaults and precedence for Project key**
There is no default key, because the CLI cannot guess which body of work the caller means.
The value comes only from this command-line option and is never read from an environment variable or a configuration file.
A key that already exists in the catalog is refused rather than overwritten, so creation never silently replaces an existing project or its history.
A leftover memory file with the same name is also treated as an existing project, which protects feedback that outlived a damaged catalog entry.
The trimmed key is the canonical form, and the same trimming is applied wherever a key is accepted later.
No other option can change the key after creation, and there is no rename command in this version.

**Project key output contract**
On success the command returns a suggestions.project.created document whose data holds the key, title, description, and linked memory file.
Human output prints a single confirmation line naming the created key.
The memory file link is always the relative path projects slash key dot json inside the suggestion data directory, and it is recorded in the catalog.
The command writes the memory file before it publishes the catalog entry, so a listed project always has a readable memory file.
If publishing the catalog fails, the new memory file is removed again so the same key can be retried cleanly.
Errors go to the error channel as typed envelopes, and stdout stays empty when creation fails.

**How to use Project key**
Pick a short lowercase name for the work the suggestions will be about, joining words with hyphens.
Pass it together with a title and a description in one project create call.
Save the key wherever the parent agent keeps durable notes, because every later feedback call and project run needs it.
Reuse the same key for every run and every reaction about that work rather than creating a new project per session.
If a create call reports that the key exists, list the projects and decide whether the existing one is the right scope before choosing another key.
Keep the key free of secrets, since it is printed in listings and embedded in the feedback commands a run returns.

```text
vidbyte-cli agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
```

**Examples for Project key**
A repository-scoped key such as vidbyte-cli collects every reaction about suggestions for that one codebase.
A goal-scoped key such as q3-onboarding collects reactions about a single long-running objective that spans several repositories.
An area-scoped key such as billing_api narrows memory to one component when feedback about neighbouring areas would mislead the generator.
A rejected example is a key with uppercase letters or a slash, which fails before anything is written and can simply be retyped.
JSON output returns the created key in the document data, which is the value to store for later calls.
If a key collides with an existing project, choose a more specific key only after confirming the existing project is not the right one.

```text
vidbyte-cli agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
vidbyte-cli --json agents suggest project create --key "{project-key}" --title "{title}" --description "{description}"
```

**Related commands for Project key**
Use agents suggest project list to see every registered key before creating a new one.
Use agents suggest run with the project option and this key to load the project's memory into a suggestion run.
Use agents suggest feedback accept with this key to record a suggestion the user explicitly wanted.
Use agents suggest feedback reject with this key to record a suggestion the user explicitly refused.
The key is the only value these commands share, so an exact match is what connects them.
None of these commands creates a project implicitly, which is why creation with this key must come first.

**Failure modes for Project key**
A missing key fails as a usage error before any validation of the other fields.
A key that is too long, begins with a hyphen or underscore, or contains uppercase or path characters fails as an invalid project.
A key already present in the catalog fails as an existing project and leaves the existing entry and its feedback untouched.
A memory file already present under the key's name also fails as an existing project rather than being replaced.
An unreadable or malformed catalog fails as unreadable project state, because adding to a broken catalog could discard the projects it lists.
Recover by correcting the key's characters, choosing an unused key, or repairing the named invalid file before retrying.

**Authentication and permissions for Project key**
Creating a project requires no Vidbyte login, API key, or model provider.
The key is written only to the local catalog and memory file inside the platform-native Vidbyte data directory.
Nothing about the key is sent to Vidbyte or to any provider by this command.
The command needs permission to create and replace files in that data directory, and it reports a write failure when the filesystem refuses.
A key grants no permission of its own, and knowing a key does not let a caller do anything beyond reading or appending to that local project.
Repair permission problems at the data directory rather than by choosing a different key.
