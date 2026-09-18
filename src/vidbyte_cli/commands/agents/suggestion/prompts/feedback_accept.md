Feedback accept records one suggestion that the user explicitly accepted for an existing local project. The suggestion text and the user's optional reason are appended to that project's memory, after every earlier record, so later project-backed runs can recognize which directions and qualities the user found useful.

Call it only when the acceptance is clear, such as the user saying they want to do the idea or choosing it over the alternatives. Do not infer acceptance from silence, from the user moving on, or from the user implementing unrelated or merely similar work. When the user explains why they liked the idea, pass that explanation as the reason, because it lets the generator look for the same property in future ideas.

The project must already exist, and an unknown or malformed key fails before any file is changed. The memory file is replaced atomically, so a failed write leaves the previous history intact and reports no success.

The command is local and deterministic. It needs no credentials, makes no model call, and does not execute or approve the suggestion. JSON output returns the project key and the stored record, and human output prints one confirmation line.
