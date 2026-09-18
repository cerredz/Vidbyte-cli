**Feedback project**
Feedback project is the key of the existing local project whose memory should receive this accepted or rejected reaction.
It selects exactly one project catalog entry and, through it, exactly one per-project memory file to append to.
The project must have been created earlier with agents suggest project create, because feedback never creates a project on its own.
Every reaction recorded under the same key joins one ordered history that later project-backed runs load as context.
The value is usually copied from the feedback commands a project-backed run returns, which already contain the right key.
Getting the key right matters more than any other field, because a reaction filed under the wrong project teaches the wrong scope.

**Purpose of Feedback project**
The purpose of Feedback project is to attach the user's reaction to the body of work it was actually about.
Suggestions are only comparable within one scope, so a rejection recorded against one repository must not steer suggestions for another.
The key keeps each project's memory separate even when several projects exist on the same machine.
It also lets a parent agent record feedback in a later session than the run that produced the suggestion, as long as it still knows the key.
A single stable key per project is what turns scattered reactions into a history the generator can learn from.
That history is read in full on the next project-backed run, so the recorded reaction takes effect immediately.

**When not to use Feedback project**
Do not guess a key when the right project is unclear, because a misfiled reaction silently distorts that project's future suggestions.
Do not record feedback under a project whose scope does not match the suggestion, even if it is the only project that exists.
Do not create a new project just to record one reaction, since that reaction would then never be seen by runs on the real project.
Avoid reusing a key across unrelated work merely because it is short or familiar.
If the suggestion came from a stateless run, decide which project it belongs to before recording anything.
When no project fits, create one with a clear scope first and record the feedback there.

**Feedback project inputs**
The value is one project key of 1 to 64 lowercase letters, numbers, hyphens, or underscores, beginning with a letter or number.
Whitespace around the key is trimmed before validation, and any other character makes the key invalid.
The key must already be present in the local project catalog.
The option is required, so the command refuses to run without it.
A malformed key fails before the catalog is opened, and an unknown key fails before the memory file is touched.
Only one project may receive a given reaction, so recording the same reaction for two projects takes two calls.

**Defaults and precedence for Feedback project**
There is no default project, because recording feedback against an assumed scope would be worse than recording nothing.
The key comes only from this option and is never read from an environment variable, a configuration value, or the current directory.
The key is not created implicitly when it is missing from the catalog.
The trimmed key is the canonical form and must match the stored key exactly.
A project-backed run's result supplies the key already filled into its feedback commands, which is the most reliable source for it.
Other feedback options do not influence which project is selected.
Passing the key explicitly on every call is what keeps a reaction from ever landing in a project the caller did not intend.

**Feedback project output contract**
On success the command returns a suggestions.feedback.recorded document whose data names the project key and the stored feedback record.
Human output prints one confirmation line naming the reaction type and the project key.
The reaction is appended to the end of that project's memory file, after every earlier record.
Nothing in the project catalog changes when feedback is recorded, because feedback lives only in the linked memory file.
The memory file is replaced atomically, so a reader sees either the previous history or the new one and never a partial file.
Errors go to the error channel as typed envelopes, and stdout stays empty when recording fails.

**How to use Feedback project**
Take the key from the feedback commands printed by the project-backed run whose suggestion the user reacted to.
When those commands are not available, list the projects and pick the key whose title and description match the suggestion's scope.
Pass the key with the suggestion text and, when available, the user's reason.
Record the reaction as soon as the user states it clearly, so the next run already benefits from it.
Keep using the same key for every later reaction about the same work.
If the command reports an unknown project, correct the key rather than creating a new project with a similar name.

```text
vidbyte-cli agents suggest feedback accept --project "{project-key}" --suggestion "{suggestion}"
```

**Examples for Feedback project**
A typical example records the user's acceptance of one suggestion under the project the run was made for.
A second example records a rejection with a reason under the same key so the next run avoids that direction.
A recovery example lists the projects first because the session no longer remembers which key was used.
A mistaken example passes a key with capital letters, which fails immediately and can be retyped in lowercase.
JSON output returns the key and the stored record, which lets another agent confirm where the reaction landed.
If a call fails because the project is missing, create or locate the project and repeat the same call.

```text
vidbyte-cli agents suggest feedback accept --project "{project-key}" --suggestion "{suggestion}"
vidbyte-cli agents suggest feedback reject --project "{project-key}" --suggestion "{suggestion}" --reason "{reason}"
vidbyte-cli --json agents suggest project list
```

**Related commands for Feedback project**
Use agents suggest project list to find an existing key and confirm its scope.
Use agents suggest project create when no existing project matches the work the suggestion was about.
Use agents suggest run with the project option to load this project's accumulated feedback into the next run.
Use the sibling feedback verb when the user's reaction was the opposite disposition.
The same key connects all of these commands, and nothing else links a reaction to a project.
None of these commands calls a model except the suggestion run itself.
Reading the project list before a first feedback call in a new session is the cheapest way to avoid filing a reaction under the wrong key.

**Failure modes for Feedback project**
A missing key fails as a usage error before anything is read.
A key with invalid characters fails as an invalid project before the catalog is opened.
A well-formed key absent from the catalog fails as a missing project, and no file is created or changed.
A catalog or memory file that is malformed, missing, or belongs to another key fails as unreadable project state.
A filesystem refusal while replacing the memory file fails as a write failure, and the previous history stays intact.
Recover by correcting the key, creating the project, or repairing the named file, then repeat the same call.

**Authentication and permissions for Feedback project**
Recording feedback requires no Vidbyte login, API key, or model provider.
The command reads the local catalog and replaces one local memory file inside the platform-native Vidbyte data directory.
Nothing is sent to Vidbyte or to any provider when feedback is recorded.
The command needs permission to replace files in that data directory and reports a write failure when the filesystem refuses.
Knowing a project key grants no additional permission, since every project is local to this machine and user.
Repair permission problems at the data directory rather than by recording feedback under a different project.
Because the memory stays local, removing the project's files is the only way to erase its recorded feedback.
