A dry run validates and resolves the complete request without invoking a model. It exposes settings, manifest entries, omissions, and warnings before reasoning incurs cost or latency.

File bodies stay out of the result by default while source identity and inclusion status remain inspectable. This makes large or sensitive context sets easier to audit safely.

No provider credentials or token usage are required for this validation path. The result contains no ideas and clearly identifies dry-run completion as its stopping reason.
