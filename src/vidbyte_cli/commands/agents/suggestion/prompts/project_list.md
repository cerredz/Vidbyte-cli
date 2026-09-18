Project list prints every local suggestion project registered in the catalog, sorted by key. Each entry shows the key, the title, and the description, which is enough to choose the right project for a run or a feedback call without opening any memory file.

Use it at the start of a session that does not remember which projects exist, before creating a new project to avoid a duplicate, and whenever a feedback or run command reports an unknown key. The listing reads only the catalog, so it never loads feedback bodies and stays fast however long a project's history grows.

An absent catalog means no project has been created yet and returns an empty successful result rather than an error. A catalog that exists but is malformed, unreadable, or in an unsupported schema fails as unreadable project state, because treating it as empty would hide projects that still have feedback on disk.

The command needs no credentials and makes no model call. JSON output returns a projects array whose entries carry key, title, description, and memory_file, while human output prints one block per project.
