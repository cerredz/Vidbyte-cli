**Project**
Project is the key of one local suggestion project whose stored memory this run should load as context.
A project is a small record on this machine made of a stable key, a human title, a scope description, and an ordered history of explicit accepted and rejected suggestions.
The key is created once with agents suggest project create and then reused by every later run and every feedback call about the same body of work.
When this option is present, the run reads the project title and description plus every recorded reaction and adds them to the bounded context before generation starts.
When this option is absent, the run is stateless and reads no project file at all, which keeps ordinary runs reproducible from argv alone.
The project gives a parent agent a durable memory of what the user already liked and refused, so it no longer has to restate that history by hand on every run.

**Purpose of Project**
The purpose of Project is to let suggestions improve across runs on the same work instead of starting from nothing every time.
A project records which directions the user explicitly accepted, which ones the user explicitly rejected, and why, when the user gave a reason.
Loading that memory lets the generator lean toward the qualities of accepted ideas and away from directions the user already turned down.
Rejected suggestions are also used by deterministic selection, so an idea that repeats a rejected suggestion verbatim is removed before ranking.
The project title and description tell the generator what body of work the feedback belongs to, so reactions are interpreted inside the right scope.
The result of a project-backed run also returns ready-to-fill feedback commands, which closes the loop between suggesting, asking the user, and remembering the answer.

**When not to use Project**
Do not pass Project for a one-off question that has no relationship to earlier or later runs on the same work.
Omit it when the stored feedback belongs to a different scope, because reactions to another codebase or goal would mislead the generator rather than help it.
Do not create a new project for every run just to have a key, since an empty project adds only its title and description and fragments the history the feature exists to keep.
Do not use a project as a place to store instructions, credentials, private data, or execution authority, because its contents are read as ordinary task data.
Use the ordinary context options instead when the signal is about this run only, such as a current constraint, a decision, or a risk.
If the project memory might be stale or wrong, repair the feedback history first rather than asking the generator to ignore part of it.

**Project inputs**
The value is one project key made of 1 to 64 lowercase letters, numbers, hyphens, or underscores, beginning with a letter or number.
Surrounding whitespace is trimmed before the key is checked, and a key with uppercase letters, slashes, dots, or other characters is rejected before any file is read.
The key must already exist in the local project catalog, because a run never creates a project implicitly.
Only one project may be supplied per run, so a run's memory always comes from exactly one scope.
The project title and description are loaded as one context kind named project, while accepted and rejected reactions are loaded as the accepted_feedback and rejected_feedback kinds.
Each reaction becomes its own context item, with the user's reason on the line after the suggestion when a reason was recorded.
Project items are subject to the same per-item and total context bounds as caller-supplied flags, so a very long history is truncated or omitted visibly rather than silently.

**Defaults and precedence for Project**
The default is no project, which means a stateless run that reads no project catalog and no memory file.
Nothing selects a project implicitly, so neither an environment variable, a configuration value, nor the current directory can turn project memory on.
When a project is supplied, its items are appended after every caller-supplied context flag, so caller references keep their numbering and project items follow them.
Caller context and project memory are both kept, and neither overrides the other, so a caller can add a current constraint that narrows what past feedback suggests.
Other settings such as count, categories, rounds, and provider stay independent and are not stored in the project.
The feedback history is read fresh on every run, so a reaction recorded a moment ago is already part of the next run's context.
The result manifest records each project item with its reference, kind, size, and inclusion status, exactly like any other context item.

**Project output contract**
A project-backed result carries the project key in its project_key field so a downstream agent can tell which memory shaped the slate.
The result also carries a feedback_capture object with an instruction plus one accept command and one reject command already filled in with this project key.
Human output prints the same accept and reject commands after the ranked ideas, so a person or agent can record the user's reaction without reading help again.
A stateless run returns a null project_key and a null feedback_capture, which is how a caller can confirm that no project file was read.
Dry-run output still resolves the project and lists its items in the manifest, which makes dry-run the safe way to inspect what memory a run would load.
The project option never grants execution authority, never records feedback by itself, and never changes the project files it reads.

**How to use Project**
Create the project once with a key, a short title, and a description of its scope.
Pass that key with this option on every suggestion run that concerns the same work.
After showing the ideas to the user, record the user's clear acceptance or rejection with the feedback command printed in the result.
Include the user's reason whenever the user gives one, because the reason tells the next run which quality mattered rather than only which idea.
Use project list to recover a key when a new session does not know which projects already exist.
Run with dry-run first when you want to see exactly which project items would enter the context before any model is called.

```text
vidbyte-cli agents suggest run --project "{project-key}" --goal "{goal}"
```

**Examples for Project**
A minimal example runs one suggestion pass with the memory of an existing project and nothing else beyond the goal.
A normal example adds a current constraint so the run respects both the stored history and a fact that is only true today.
An inspection example uses dry-run with JSON output to list the project items in the manifest without calling a provider.
A full loop creates the project, runs with it, records the user's rejection with a reason, and runs again so the next slate avoids that direction.
JSON output is the stable choice when another agent will read project_key, feedback_capture, and the manifest programmatically.
If an example fails with a missing project, list the catalog and correct the key before changing any other option.

```text
vidbyte-cli agents suggest run --project "{project-key}" --goal "{goal}"
vidbyte-cli agents suggest run --project "{project-key}" --goal "{goal}" --constraint "{constraint}"
vidbyte-cli --json agents suggest run --project "{project-key}" --goal "{goal}" --dry-run
vidbyte-cli agents suggest feedback reject --project "{project-key}" --suggestion "{suggestion}" --reason "{reason}"
```

**Related commands for Project**
Use agents suggest project create to register a new key with its title and description before the first project-backed run.
Use agents suggest project list to see every existing key, title, and description without opening any feedback file.
Use agents suggest feedback accept to record a suggestion the user clearly wanted, together with the reason when one was given.
Use agents suggest feedback reject to record a suggestion the user clearly refused, so later runs stop proposing that direction.
Use agents suggest handoff after a project-backed run exactly as after a stateless one, since the saved result keeps the same shape.
These commands share one local project store, but none of them calls a model except the run itself.

**Failure modes for Project**
A key that does not match the allowed character pattern fails as an invalid project before any file is read.
A well-formed key that is not in the catalog fails as a missing project, and nothing is created in its place.
A catalog or memory file that is not valid JSON, does not match its schema, or belongs to a different key fails as unreadable project state.
A memory file that the catalog links to but that is missing from disk also fails as unreadable state rather than being treated as an empty history.
None of these failures calls a model or changes any project file, so the invocation can be corrected and retried safely.
Recover by listing projects to confirm the key, then repair or remove only the named invalid file if the state itself is broken.

**Authentication and permissions for Project**
Reading project memory requires no Vidbyte login, API key, or provider credential.
Project files live only in the platform-native Vidbyte data directory on this machine and are never uploaded by this option.
The run reads exactly the catalog and the one memory file linked to the supplied key and scans nothing else.
A model-backed run still needs its configured provider, while a dry run resolves the project without any provider at all.
Permission errors on the data directory surface as unreadable project state and are repaired at the filesystem, not by weakening the option.
Project contents are passed to agents as task data only and never grant the generator or critic any permission to act.
