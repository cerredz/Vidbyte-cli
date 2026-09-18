Feedback reject records one suggestion that the user explicitly rejected for an existing local project. The suggestion text and the user's optional reason are appended to that project's memory, after every earlier record, so later project-backed runs stop proposing the same unwanted direction.

Rejected feedback has two effects on the next run with this project. The generator reads the rejection and its reason as context and steers away from ideas with the same drawback, and deterministic selection removes any idea whose title, summary, or actions repeat the rejected suggestion text word for word.

Call it only when the rejection is clear, such as the user saying no or explaining why the idea does not fit. Do not infer rejection from silence, a change of topic, or the user simply not acting on the idea yet. A reason is especially valuable here, because it lets one rejection rule out a whole family of similar ideas rather than one wording.

The project must already exist, and an unknown or malformed key fails before any file is changed. The command is local and deterministic, needs no credentials, makes no model call, and never removes earlier feedback. JSON output returns the project key and the stored record, and human output prints one confirmation line.
