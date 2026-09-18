**Feedback suggestion**
Feedback suggestion is the text of the suggestion the user explicitly accepted or rejected.
It is stored verbatim in the project's memory and becomes one context item on every later run that loads the project.
The text should identify the direction clearly enough that a future generator can recognize it without the original result document.
Usually that means the suggestion's title, optionally followed by the short summary or first action that made the direction concrete.
The value is preference history, not a task, so recording it never executes, schedules, or approves any work.
For rejected feedback the verbatim text is also used to remove later ideas that repeat it word for word.

**Purpose of Feedback suggestion**
The purpose of Feedback suggestion is to preserve which direction the user reacted to, in words the next run can match against.
Accepted suggestions show the generator which qualities of an idea were useful, so it can propose more ideas with those qualities.
Rejected suggestions show the generator which directions to stop proposing, and the exact text lets deterministic selection filter verbatim repeats.
Storing the text rather than an idea identifier keeps the memory meaningful after the original result file is gone.
A clear record also lets a person audit the project memory later and understand each decision without reconstructing old runs.
The more precisely the text names the direction, the less the generator has to guess about what the user meant.

**When not to use Feedback suggestion**
Do not record a suggestion the user has not clearly reacted to, because silence, a topic change, or partial interest is not feedback.
Do not record an idea as accepted merely because the user later implemented something similar, unless the user said so.
Do not paraphrase the suggestion into a different claim, since that records a reaction the user never gave.
Avoid pasting an entire result document, because a long record dilutes the signal and may be truncated in later runs.
Do not use this field to leave instructions for the generator, since it is loaded as data and never as a directive.
If the user reacted to several suggestions, record each one in its own call rather than joining them into one text.

**Feedback suggestion inputs**
The value is one string of at most 8192 characters that is not empty or whitespace only.
Surrounding whitespace is preserved exactly as supplied, so the stored text matches what the caller passed.
Quotes, punctuation, and line breaks inside a quoted shell argument are all accepted.
The option is required, so the command refuses to run without it.
Validation happens in the feedback input dataclass before the project catalog is opened.
The text is not compared against earlier records, so recording the same suggestion twice keeps both entries as history.
Because the text is stored verbatim, the caller controls exactly what later runs will see and what rejected suggestions will match.

**Defaults and precedence for Feedback suggestion**
There is no default suggestion text, because only the caller knows which direction the user reacted to.
The value comes only from this option and is never read from a saved result file, an environment variable, or configuration.
The reaction type comes from the command name, accept or reject, and never from anything inside this text.
Records are appended in call order, so the history reflects the order in which reactions were recorded.
An earlier record is never edited or removed by a later one, even when the later record has the opposite disposition.
When accepted and rejected records about the same direction coexist, both are loaded and the generator weighs them together.

**Feedback suggestion output contract**
On success the returned document's feedback record includes the suggestion text exactly as stored.
The record also includes the reaction type, the optional reason, and a UTC creation timestamp.
On later project-backed runs the text appears in context as Accepted suggestion or Rejected suggestion followed by the stored words.
When a reason was recorded, it appears on the next line after the suggestion text in that same context item.
Human output prints only a confirmation line, while JSON output includes the full stored record.
Errors about the text are reported as invalid feedback without echoing the rejected value.
The stored record is never altered by later calls, so the returned document remains an accurate description of what was saved.

**How to use Feedback suggestion**
Copy the suggestion's title from the result the user reacted to, and add its summary when the title alone is ambiguous.
Pass it in quotes with the project key using the accept or reject verb that matches the user's reaction.
Record one suggestion per call so each reaction keeps its own reason and timestamp.
Keep the wording close to the original so rejected text can match a repeated idea exactly.
Add the user's reason with the reason option whenever the user explained the reaction.
Record the reaction promptly so the next run in the same session already reflects it.
Short, specific wording is easier for the next run to recognize than a long paragraph copied from the result.

```text
vidbyte-cli agents suggest feedback reject --project "{project-key}" --suggestion "{suggestion}"
```

**Examples for Feedback suggestion**
An acceptance example records a suggested caching layer by its title because the user said they want to build it next.
A rejection example records a suggestion to adopt a new database because the user said the project must avoid new infrastructure.
A detailed example records a title followed by its first action because two earlier ideas shared similar titles.
A mistaken example records a whole result document, which is valid but wastes context and may be truncated later.
JSON output shows the stored record, which confirms the exact text that later runs will see.
If a call fails as invalid feedback, supply nonempty text within the length bound and repeat the call.

```text
vidbyte-cli agents suggest feedback accept --project "{project-key}" --suggestion "{suggestion}"
vidbyte-cli agents suggest feedback reject --project "{project-key}" --suggestion "{suggestion}" --reason "{reason}"
```

**Related commands for Feedback suggestion**
Use agents suggest run with the project option to generate the suggestions whose text you record here.
Use the feedback commands printed in a project-backed result as a template with the key already filled in.
Use agents suggest handoff when the user accepted an idea and another agent needs its full action packet.
Use the reason option on this same command to store why the user reacted as they did.
Use agents suggest project list to confirm which project a suggestion belongs to before recording it.
None of these commands executes the suggestion, and recording feedback never starts work.
Keeping these steps separate means the caller always decides explicitly when a reaction is recorded.

**Failure modes for Feedback suggestion**
A missing suggestion option fails as a usage error before anything is read.
Text that is empty or whitespace only fails as invalid feedback and nothing is written.
Text longer than 8192 characters fails as invalid feedback with the bound named in the error.
A valid text can still fail to be recorded when the project is unknown or its memory file is unreadable.
A filesystem refusal while replacing the memory file fails as a write failure, and earlier records stay intact.
Recover from a text failure by shortening or supplying the suggestion, then repeat the same call.
No failure ever records a partial reaction, so a retry cannot create a duplicate of a record that was never saved.

**Authentication and permissions for Feedback suggestion**
Recording suggestion text requires no Vidbyte login, API key, or model provider.
The text is written only to the project's local memory file inside the platform-native Vidbyte data directory.
It leaves the machine only when a later model-backed run with this project sends its context to the configured provider.
Recording feedback grants no permission to any agent and cannot authorize the suggestion it names.
The command needs permission to replace the memory file and reports a write failure when the filesystem refuses.
Keep secrets and private data out of the text because it is shared with the provider on real project-backed runs.
