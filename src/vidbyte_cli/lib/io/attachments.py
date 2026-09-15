"""Resolves explicit local agent attachments into bounded immutable snapshots.

This module owns generic filesystem access for future agent commands. It does not attach an
option to a command, launch a provider, or expand directories and globs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ...types.attachments import AgentAttachment, AttachmentBundle, AttachmentKind
from ..constants.runtime import AttachmentImageSuffix, AttachmentLimit
from ..errors.failures import (
    AttachmentDirectory,
    AttachmentDuplicate,
    AttachmentEmpty,
    AttachmentFileNotFound,
    AttachmentInputInvalid,
    AttachmentLimitExceeded,
    AttachmentTooLarge,
    AttachmentUnreadable,
    AttachmentUnsupported,
)


class AttachmentResolver:
    """Reads an ordered, explicit set of files into one validated attachment bundle."""

    def resolve(self, paths: tuple[Path, ...]) -> AttachmentBundle:
        # Validates collection shape and limits before touching any caller path.
        self._validate_input(paths)
        if not paths:
            return AttachmentBundle()
        items: list[AgentAttachment] = []
        seen: set[Path] = set()
        total_bytes = 0
        for path in paths:
            item = self._resolve_one(path, seen, total_bytes)
            total_bytes += item.size_bytes
            if total_bytes > int(AttachmentLimit.MAX_TOTAL_BYTES):
                raise AttachmentLimitExceeded()
            items.append(item)
        return AttachmentBundle(items=tuple(items), total_bytes=total_bytes)

    def _validate_input(self, paths: tuple[Path, ...]) -> None:
        # Rejects values outside Click's tuple-of-Path contract before accidental iteration.
        if not isinstance(paths, tuple) or any(not isinstance(path, Path) for path in paths):
            raise AttachmentInputInvalid()
        if len(paths) > int(AttachmentLimit.MAX_FILES):
            raise AttachmentLimitExceeded()

    def _resolve_one(self, path: Path, seen: set[Path], total_bytes: int) -> AgentAttachment:
        # Resolves one file, hashes its exact bytes, and classifies it without a second read.
        resolved = self._resolved_path(path)
        if resolved in seen:
            raise AttachmentDuplicate()
        seen.add(resolved)
        raw = self._read_bytes(resolved)
        size_bytes = len(raw)
        if size_bytes == 0:
            raise AttachmentEmpty()
        if size_bytes > int(AttachmentLimit.MAX_FILE_BYTES):
            raise AttachmentTooLarge()
        if total_bytes + size_bytes > int(AttachmentLimit.MAX_TOTAL_BYTES):
            raise AttachmentLimitExceeded()
        digest = hashlib.sha256(raw).hexdigest()
        if self._is_image(resolved):
            return AgentAttachment(
                supplied_path=path,
                resolved_path=resolved,
                name=path.name,
                kind=AttachmentKind.IMAGE,
                size_bytes=size_bytes,
                sha256=digest,
            )
        content = self._decode_text(raw)
        return AgentAttachment(
            supplied_path=path,
            resolved_path=resolved,
            name=path.name,
            kind=AttachmentKind.TEXT,
            size_bytes=size_bytes,
            sha256=digest,
            content=content,
        )

    def _resolved_path(self, path: Path) -> Path:
        # Converts path errors into a stable typed failure without exposing private paths.
        try:
            resolved = path.expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise AttachmentUnreadable() from error
        try:
            if not resolved.exists():
                raise AttachmentFileNotFound()
            if resolved.is_dir():
                raise AttachmentDirectory()
            if not resolved.is_file():
                raise AttachmentUnreadable()
        except OSError as error:
            raise AttachmentUnreadable() from error
        return resolved

    def _read_bytes(self, path: Path) -> bytes:
        # Reads one exact snapshot and hides filesystem details from the public failure.
        try:
            return path.read_bytes()
        except OSError as error:
            raise AttachmentUnreadable() from error

    def _is_image(self, path: Path) -> bool:
        # Uses the closed suffix enum so provider-native image support cannot drift silently.
        return path.suffix.lower() in {item.value for item in AttachmentImageSuffix}

    def _decode_text(self, raw: bytes) -> str:
        # Accepts UTF-8 with an optional BOM and rejects binary-looking text with NUL bytes.
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise AttachmentUnsupported() from error
        if "\x00" in content:
            raise AttachmentUnsupported()
        if not content:
            raise AttachmentEmpty()
        return content


__all__ = ["AttachmentResolver"]
