A structured request document carries a goal, contextual records, and generation settings as one validated object. It is useful when another agent already holds the task state in machine-readable form.

The document follows a versioned schema so older producers cannot silently change meaning. Malformed data, unsupported versions, and incomplete required fields are rejected before reasoning begins.

Structured request data is an alternative source for goal and context rather than a second competing source. Explicit generation controls may refine its settings while preserving one authoritative context snapshot.
