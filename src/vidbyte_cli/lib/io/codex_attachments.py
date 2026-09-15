"""Converts provider-neutral attachment snapshots into native Codex run inputs.

The SDK stays behind a lazy import boundary so importing the shared attachment layer never
starts provider work or makes `--help` depend on Codex being installed.
"""

from __future__ import annotations

from typing import Any

from ...types.attachments import AgentAttachment, AttachmentBundle, AttachmentKind


class CodexAttachmentInputBuilder:
    """Builds one CodexRunInput from a prompt and an already-resolved attachment bundle."""

    def build(self, prompt: str, bundle: AttachmentBundle) -> Any:
        # Imports occur only when a future Codex service actually starts an agent turn.
        from vidbyte.context.primitives import FileContextItem
        from vidbyte.lib.dataclasses.codex import (
            CodexLocalImageInput,
            CodexRunInput,
            CodexTextInput,
        )

        inputs: list[Any] = [CodexTextInput(prompt)]
        context_items: list[Any] = []
        for attachment in bundle.items:
            if attachment.kind is AttachmentKind.IMAGE:
                inputs.append(CodexLocalImageInput(str(attachment.resolved_path)))
            else:
                context_items.append(self._file_context(FileContextItem, attachment))
        return CodexRunInput(items=tuple(inputs), context_items=tuple(context_items))

    def _file_context(self, file_type: type[Any], attachment: AgentAttachment) -> Any:
        # Reuses the resolver's bytes and hash rather than reading a changed file again.
        return file_type(
            path=str(attachment.supplied_path),
            absolute_path=str(attachment.resolved_path),
            size_bytes=attachment.size_bytes,
            content=attachment.content,
            language=attachment.resolved_path.suffix.lstrip(".") or None,
            metadata={"sha256": attachment.sha256},
        )


__all__ = ["CodexAttachmentInputBuilder"]
