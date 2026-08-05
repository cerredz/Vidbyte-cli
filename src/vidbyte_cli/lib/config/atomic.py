"""The one way local CLI state is replaced on disk: owner-only, fsynced, atomic.

Config, the fallback credential file, and migrated copies all go through here, so the
permission and durability rules live in one reviewable place instead of at each store.

The write goes to a randomized sibling in the destination directory before `os.replace`,
because replace is only atomic within a filesystem, and an interrupted write must leave the
previous file rather than a truncated one. This layer knows nothing about JSON or secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from ..errors.failures import StateWriteFailed, StateWriteThroughSymlink


class AtomicFileWriter:
    """Write exact files through a flushed sibling and atomic replacement."""

    def write(self, path: Path, content: bytes, *, mode: int = 0o600) -> None:
        # Replacing a symlink mutates the link entry on some platforms and its target on
        # others. That is not uniform enough to stand as a security boundary for a path
        # that may hold a credential, so refuse rather than pick a behavior.
        if path.is_symlink():
            raise StateWriteThroughSymlink()
        temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # O_EXCL with a random name means this process owns the temporary file outright.
            descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # Windows ignores the mode passed to os.open, and os.replace preserves the
            # destination's existing permissions, so restate the mode on both sides.
            os.chmod(temporary_path, mode)
            os.replace(temporary_path, path)
            os.chmod(path, mode)
        except OSError as error:
            raise StateWriteFailed(error) from error
        finally:
            # Only this call's randomized sibling is ever removed, never the destination.
            temporary_path.unlink(missing_ok=True)
