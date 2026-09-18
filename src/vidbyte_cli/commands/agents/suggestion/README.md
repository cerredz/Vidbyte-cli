# Agents commands

`agents suggest run` generates ideas, `categories` lists the taxonomy, `handoff` extracts one packet. `project create` and `project list` manage local memory projects, and `feedback accept` and `feedback reject` append the user's explicit reactions to one project; `run --project KEY` loads that memory as context. Project and feedback commands never call a model. Every command and option help text is a Markdown asset under `prompts/`.
