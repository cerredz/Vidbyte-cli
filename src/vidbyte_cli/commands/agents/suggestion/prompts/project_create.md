Project create registers one new local suggestion project under a stable key, with a human-readable title and a plain-language description of its scope. The key becomes the selector every later command uses: feedback accept and feedback reject append reactions to it, and agents suggest run with the project option loads its memory into a run.

Creation writes an empty feedback memory file first and then publishes the project in the catalog, so a listed project always has a readable memory file. If the catalog cannot be written, the new memory file is removed again so the same key can be retried. A key that already exists, or whose memory file is already on disk, is refused instead of being overwritten, which keeps an existing project's feedback history safe.

Choose one project per body of work that suggestions will be about, such as a repository, a product area, or a long-running goal. Put durable scope in the description, because it frames every accepted and rejected reaction on every later run, and keep run-specific facts in the run's own context options.

The command is local and deterministic. It needs no credentials, makes no model call, and sends nothing to Vidbyte. JSON output returns the created record, including the key and its linked memory file, and human output prints one confirmation line.
