Suggestion projects give the suggestion agent a durable local memory for one body of work. A project is a stable key, a human title, a scope description, and an ordered history of suggestions the user explicitly accepted or rejected, kept on this machine in the platform-native Vidbyte data directory.

The project lifecycle has four steps. Create a project once with project create, pass its key to agents suggest run with the project option so the run loads the title, description, and every recorded reaction, record the user's clear reactions with feedback accept or feedback reject, and run again so the next slate builds on what the user liked and avoids what the user refused. Use project list at any point to recover an existing key instead of creating a duplicate.

The catalog of projects lives in one projects.json file, and each project links to its own memory file under the projects directory beside it. Every write replaces a whole document atomically, so an interrupted command leaves the previous valid state in place rather than a truncated file.

Project commands never call a model and need no Vidbyte login, API key, or provider. Only a suggestion run that passes a project key sends the project's contents to a provider, and only as task data that grants no permission to act.
