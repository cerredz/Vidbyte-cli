**Feedback reason**
Feedback reason is the user's own explanation of why they accepted or rejected the suggestion.
It is optional, and it is stored with the suggestion text in the same feedback record.
On later project-backed runs the reason appears on the line after the suggestion, so the generator learns what quality drove the reaction.
A reason often matters more than the reaction itself, because it tells the generator which neighbouring ideas would be welcome or unwelcome too.
The value should carry the user's meaning, not a rationale the calling agent invented afterwards.
Leaving it out is correct whenever the user gave a clear reaction without saying why.

**Purpose of Feedback reason**
The purpose of Feedback reason is to let one reaction generalize correctly to future ideas the user has not seen yet.
Without a reason, a rejected suggestion only tells the generator to avoid that exact direction.
With a reason such as too much new infrastructure, it can also avoid other ideas that share the same drawback.
For accepted suggestions, a reason such as small enough to ship this week tells the generator which property to look for again.
Reasons also make the project memory auditable, since a person can later see why each decision was made.
Storing the reason separately from the suggestion text keeps the suggestion matchable while still preserving the explanation.

**When not to use Feedback reason**
Do not invent a reason when the user did not give one, because a fabricated reason steers every later run in a direction the user never chose.
Do not summarize a long conversation into a reason that the user would not recognize as their own view.
Do not use the reason to give the generator instructions, since it is loaded as data and never as a directive.
Avoid restating the suggestion itself as the reason, which adds length without adding meaning.
Keep credentials, private data, and confidential details out of the reason, because it is sent to the provider on real runs.
If the user's explanation covers several suggestions, record it with each one separately rather than once for all of them.

**Feedback reason inputs**
The value is one optional string of at most 8192 characters.
When supplied, it is stored exactly as passed, including surrounding whitespace.
When omitted, the stored reason is null rather than an empty string, so absence remains distinguishable from a blank value.
Quotes, punctuation, and line breaks inside a quoted shell argument are accepted.
Validation happens in the feedback input dataclass before the project catalog is opened.
The reason is never parsed or classified, so any wording the user chose is preserved.
Because the reason is kept apart from the suggestion text, its wording never affects which later ideas are suppressed as verbatim repeats of a rejection.

**Defaults and precedence for Feedback reason**
The default is no reason, which records the reaction on its own.
The value comes only from this option and is never read from a result file, an environment variable, or configuration.
The reason never changes the reaction type, which is fixed by whether the accept or reject verb was called.
A later reaction's reason does not replace an earlier one, because each record keeps its own reason.
When several records about similar suggestions carry different reasons, all of them are loaded and weighed together on the next run.
The reason is loaded only on runs that pass this project's key, and stateless runs never see it.

**Feedback reason output contract**
On success the returned document's feedback record includes the reason, or null when it was omitted.
On later project-backed runs the reason appears in the same context item as its suggestion, on the line after the suggestion text.
Rejected-suggestion suppression uses only the suggestion text, so a reason never causes an unrelated idea to be filtered.
Human output prints only a confirmation line, while JSON output includes the full stored record.
The result manifest of a later run counts the reason inside its feedback item's size and inclusion status.
Errors about the reason are reported as invalid feedback without echoing the rejected value.

**How to use Feedback reason**
Pass the user's explanation in quotes on the same accept or reject call as the suggestion.
Keep the user's words where possible, trimming only filler that does not change the meaning.
Prefer a reason that names a property, such as cost, risk, timing, or scope, over one that only expresses a mood.
Omit the option entirely when the user did not explain the reaction.
Record one reason per suggestion so each reaction stays independently interpretable.
Check the stored record in JSON output when another agent will depend on the exact wording.
A short reason in the user's own words is more useful to the next run than a long paraphrase written by the calling agent.

```text
vidbyte-cli agents suggest feedback reject --project "{project-key}" --suggestion "{suggestion}" --reason "{reason}"
```

**Examples for Feedback reason**
A rejection example stores a reason saying the idea adds backend infrastructure the project deliberately avoids.
An acceptance example stores a reason saying the idea can be finished this week without new dependencies.
A minimal example records a clear rejection with no reason, because the user simply said no.
A mistaken example stores a reason the calling agent guessed, which should instead have been left out.
JSON output shows the stored reason or null, which confirms whether a reason reached the project memory.
If a call fails because the reason is too long, shorten it to the user's essential point and repeat the call.

```text
vidbyte-cli agents suggest feedback reject --project "{project-key}" --suggestion "{suggestion}" --reason "{reason}"
vidbyte-cli agents suggest feedback accept --project "{project-key}" --suggestion "{suggestion}" --reason "{reason}"
```

**Related commands for Feedback reason**
Use the suggestion option on the same command to store which direction the reason is about.
Use agents suggest run with the project option to have later runs read both the suggestion and its reason.
Use run-level context options instead when the explanation is a fact about the current run rather than a reaction to a suggestion.
Use agents suggest project list to confirm the right project before recording a reason under it.
Use the opposite feedback verb when the user's reason reveals the reaction was actually the other disposition.
None of these commands rewrites a stored reason, so a wrong reason is corrected by recording a new reaction.

**Failure modes for Feedback reason**
A reason longer than 8192 characters fails as invalid feedback and nothing is written.
A valid reason never fails on its wording, because the CLI does not interpret it.
The call can still fail when the suggestion text is invalid, the project is unknown, or its memory file is unreadable.
A filesystem refusal while replacing the memory file fails as a write failure, and earlier records stay intact.
Omitting the reason is never an error and always records the reaction with a null reason.
Recover from a reason failure by shortening the text to the user's essential point and repeating the same call.

**Authentication and permissions for Feedback reason**
Recording a reason requires no Vidbyte login, API key, or model provider.
The reason is written only to the project's local memory file inside the platform-native Vidbyte data directory.
It leaves the machine only when a later model-backed run with this project sends its context to the configured provider.
A reason grants no permission to any agent and cannot authorize or forbid any action on its own.
The command needs permission to replace the memory file and reports a write failure when the filesystem refuses.
Keep secrets and private data out of the reason because it is shared with the provider on real project-backed runs.
