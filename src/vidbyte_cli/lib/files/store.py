"""Product-neutral file I/O behind one store rooted at one directory.

Any command or runtime primitive that keeps local files — checkpoints, logs, reports,
exported documents — reads and writes them through this class, so atomicity, encoding, and
path resolution are decided once instead of at each call site. It knows paths and bytes only:
which file a record belongs in, and what its contents mean, is always the caller's decision.
Owner-only CLI state such as config and credentials goes through `lib/config/atomic.py`.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import tempfile
from pathlib import Path

from ..errors.failures import LocalFileReadFailed, LocalFileWriteFailed


class LocalFileStore:
    """Resolves, reads, and atomically writes files under one root directory."""

    def __init__(self, root: Path) -> None:
        # Resolving once at construction is what makes every path this store returns absolute,
        # so a file a result reports stays addressable from another working directory.
        self._root = root.expanduser().resolve()

    @property
    def root(self) -> Path:
        # The absolute directory every relative name in this store resolves against.
        return self._root

    def path_of(self, name: str | Path) -> Path:
        # One join site. An absolute name passes through unchanged, which is how a caller
        # writes a destination it was handed without building a second store for it.
        return self._root / name

    def exists(self, name: str | Path) -> bool:
        # Presence check for a regular file; a directory of the same name is not a file.
        return self.path_of(name).is_file()

    def subdirectories(self) -> tuple[Path, ...]:
        # Sorted so a listing is stable across runs and filesystems. An absent root holds
        # nothing, while a root that exists but cannot be scanned is a failure worth naming.
        if not self._root.is_dir():
            return ()
        try:
            return tuple(sorted(child for child in self._root.iterdir() if child.is_dir()))
        except OSError as error:
            raise LocalFileReadFailed(self._root.name, self.reason_for(error), error) from error

    def read_text(self, name: str | Path) -> str | None:
        # None means absent and nothing else; a file that exists but cannot be read or
        # decoded raises, so a caller never mistakes a permission problem for a missing file.
        path = self.path_of(name)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as error:
            raise LocalFileReadFailed(path.name, self.reason_for(error), error) from error

    def read_json(self, name: str | Path) -> object | None:
        # Same absent-versus-broken contract as read_text, with invalid JSON counted as broken.
        body = self.read_text(name)
        if body is None:
            return None
        try:
            parsed: object = json.loads(body)
        except ValueError as error:
            path = self.path_of(name)
            raise LocalFileReadFailed(path.name, self.reason_for(error), error) from error
        return parsed

    def write_json(self, name: str | Path, payload: object) -> Path:
        # Serializes first so a malformed payload fails before the target file is touched.
        return self.write_text(name, json.dumps(payload))

    def write_text(self, name: str | Path, body: str) -> Path:
        # Writes through a temp sibling plus os.replace, so a reader never sees a partial file
        # and a crash mid-write leaves the previous version intact rather than a truncated one.
        target = self.path_of(name)
        temporary: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
            )
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(body)
            os.replace(temporary, target)
            return target
        except (OSError, UnicodeError) as error:
            self._discard(temporary)
            raise LocalFileWriteFailed(target.name, self.reason_for(error), error) from error

    def append_line(self, name: str | Path, body: str) -> Path:
        # Append is deliberately not atomic: an append-only log is read by outside tools that
        # tail it, and rewriting it per record would break every reader holding an offset.
        path = self.path_of(name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"{body}\n")
        except (OSError, UnicodeError) as error:
            raise LocalFileWriteFailed(path.name, self.reason_for(error), error) from error
        return path

    def copy_into(self, name: str | Path, destination: Path) -> Path:
        # Duplicates rather than moves or links, so the source stays readable and unchanged
        # whatever the copy goes on to become.
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.path_of(name), destination)
        except OSError as error:
            raise LocalFileWriteFailed(destination.name, self.reason_for(error), error) from error
        return destination

    @staticmethod
    def reason_for(error: BaseException) -> str:
        # A fixed category rather than the operating system's own message, so no absolute
        # path or platform wording reaches an error, and the category alone names the repair.
        # UnicodeError precedes ValueError because it is the more specific subclass.
        match error:
            case FileNotFoundError():
                return "the file or one of its parent directories does not exist"
            case PermissionError():
                return "permission was denied"
            case IsADirectoryError():
                return "the path names a directory, not a file"
            case NotADirectoryError() | FileExistsError():
                return "a parent of the path is a file, not a directory"
            case UnicodeError():
                return "the content is not valid UTF-8 text"
            case ValueError():
                return "the content is not valid JSON"
            case OSError() if error.errno == errno.ENOSPC:
                return "the volume is full"
            case OSError() if error.errno == errno.EROFS:
                return "the volume is read-only"
            case RuntimeError():
                return "the path could not be resolved, such as an unexpandable ~ or a link loop"
            case _:
                return "the operating system refused the operation"

    @staticmethod
    def _discard(temporary: str | None) -> None:
        # Only this call's own temp sibling is ever removed, never the destination.
        if temporary is None:
            return
        try:
            os.unlink(temporary)
        except OSError:
            pass
