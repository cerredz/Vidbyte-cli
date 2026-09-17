Extra compute runs one independent suggestion agent for each selected category and combines their structured results before whole-slate refinement. Each category receives the same goal and caller context, but its own focused category window, so the run can explore more distinct directions.

The default is off because one shared window is usually enough and uses fewer model turns. Enable it when breadth matters more than latency or when several categories deserve separate attention. The combined pool is still bounded by the requested count and the workflow's total token and time limits.

This setting changes the generation topology, not the meaning of a category or the final schema. Every per-category result is labeled before combination, and the independent critic still reviews the combined candidates. A provider failure stops the provider-backed run with its typed error so the caller never mistakes a partial pool for a complete result.
