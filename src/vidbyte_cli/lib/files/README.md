# `src/vidbyte_cli/lib/files`

Owns product-neutral file I/O for data a command or runtime primitive keeps on disk:
checkpoints, append-only logs, reports, and exported documents. One `LocalFileStore` is rooted
at one directory, so atomic replacement, UTF-8 encoding, path resolution, and the wording of a
filesystem failure are decided once rather than at every call site.

**Blast radius:** every primitive that persists local files. A changed return contract — what
`read_text` returns for an absent file, or which failure a write raises — changes how each
caller tells a missing file from a broken one.

## Non-goals

- No product semantics. Which file a record belongs in, and what its bytes mean, is the
  caller's decision; nothing here may import a command, a service, or a primitive.
- No owner-only CLI state. Config and credential files go through `lib/config/atomic.py`,
  which also sets permissions and fsyncs.
- No raw `OSError` escaping to a caller. Every filesystem failure becomes
  `LocalFileReadFailed` or `LocalFileWriteFailed`, carrying a fixed reason category rather
  than the operating system's message, so callers can re-raise it with their own context.

## Files

- `__init__.py` — the public facade.
- `store.py` — `LocalFileStore`: absolute path resolution, absent-versus-unreadable reads,
  atomic writes through a temp sibling, appends, copies, directory scans, and the fixed
  reason categories every failure carries.
- `documents.py` — `LocalDocumentStore`: versioned JSON documents on top of `LocalFileStore`,
  taking the pydantic model as a parameter. It bounds document size, refuses a name that
  escapes its root, raises `LocalDocumentInvalid` for a present-but-wrong document, and writes
  sorted, indented JSON so documents stay byte-stable.

## Log

- 2026-09-10 — Lifted out of `lib/runtime_primitives/task_board_files.py` (PR #46 review) so
  every command and primitive can share it; task-list parsing stayed with the task board.
- 2026-09-18 — `LocalDocumentStore` added (PR #84 review) so a feature keeping a catalog plus
  linked records gets model-validated reads and contained names from one general class
  instead of per-feature read/write/path helpers.
