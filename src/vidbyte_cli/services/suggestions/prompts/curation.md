# Suggestion curation

Review the active suggestions in the context and the critic feedback in the system prompt.
Use the provided tools to make only evidence-grounded changes to the active store.
Preserve a suggestion's stable identifier when updating it by passing its identifier in the draft.
Remove suggestions that cannot be repaired, and add replacements only when they are materially
distinct from the active slate. Call `more_suggestions` only when the slate is genuinely short or
missing a useful category, then return a completion receipt without commentary outside the schema.

Goal: {{goal}}
The current active slate contains {{count}} suggestions.
