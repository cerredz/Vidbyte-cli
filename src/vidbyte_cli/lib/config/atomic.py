"""FILE: src/vidbyte_cli/lib/config/atomic.py

PURPOSE: Performs permission-restricted, same-directory atomic file replacement for local
CLI state. It is the shared mutation primitive for configuration, fallback credentials,
migration copies, and later operation journals.

ROLE IN CODEBASE: Stores validate domain documents before passing encoded bytes here.
AtomicFileWriter owns filesystem mechanics but has no knowledge of JSON or secrets.

ARCHITECTURE NOTE: A sibling temporary file is flushed and fsynced before os.replace().
Existing symlink targets are rejected so a CLI write cannot be redirected unexpectedly.

FUNCTION INVENTORY (reviewed 2026-07-26):
- AtomicFileWriter.write(path, content, mode) -> None: atomically replaces one exact file.

WHAT NOT TO DO IN THIS FILE:
1. Do not serialize domain models or produce user-facing output.
2. Do not recursively remove directories or follow write-target symlinks.
3. Do not include file contents in exceptions or diagnostics.
4. Do not weaken owner-only modes for credential-bearing files.

TESTS: Covered by lint, strict typing, compilation, and public smoke under the approved
no-tests workflow.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from ..errors import CliError, CliErrorCode


class AtomicFileWriter:
    """Write exact files through a flushed sibling and atomic replacement."""

    def write(self, path: Path, content: bytes, *, mode: int = 0o600) -> None:
        # @intent reject-symlinked-state-write-targets
        # Config and credential paths may contain attacker-controlled data. Replacing a
        # symlink would mutate its link entry on common platforms, but platform behavior is
        # not sufficiently uniform to make that an acceptable security boundary.
        if path.is_symlink():
            raise CliError(
                CliErrorCode.CONFIG_INVALID,
                "Refusing to write CLI state through a symbolic link.",
                hint="Replace the symbolic link with a regular file and retry.",
            )
        temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                mode,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_path, mode)
            os.replace(temporary_path, path)
            os.chmod(path, mode)
        except CliError:
            raise
        except OSError as error:
            raise CliError(
                CliErrorCode.OPERATION_FAILED,
                "CLI state could not be saved.",
                hint="Check directory ownership and available disk space, then retry.",
                cause=error,
            ) from error
        finally:
            # The exact randomized sibling is safe to remove after a failed pre-replace write.
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
