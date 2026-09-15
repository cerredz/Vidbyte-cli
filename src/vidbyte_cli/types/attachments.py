"""Provider-neutral contracts for explicit files supplied to future agent invocations.

These models describe one immutable snapshot and its body-free output manifest. Filesystem
access and provider-specific conversion belong to the I/O layer, not to these contracts.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AttachmentKind(StrEnum):
    """The two file forms the first shared attachment contract supports."""

    TEXT = "text"
    IMAGE = "image"


class AgentAttachment(BaseModel):
    """One validated file snapshot with provenance and integrity metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supplied_path: Path
    resolved_path: Path
    name: str = Field(min_length=1, max_length=256)
    kind: AttachmentKind
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str | None = None

    @model_validator(mode="after")
    def validate_content_shape(self) -> AgentAttachment:
        # Images use the native path input; text attachments carry the captured body.
        if self.kind is AttachmentKind.TEXT and not self.content:
            raise ValueError("text attachments require content")
        if self.kind is AttachmentKind.IMAGE and self.content is not None:
            raise ValueError("image attachments cannot carry text content")
        return self


class AttachmentBundle(BaseModel):
    """An ordered immutable attachment collection resolved for one invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[AgentAttachment, ...] = ()
    total_bytes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_totals_and_paths(self) -> AttachmentBundle:
        # The bundle owns the aggregate invariants so programmatic callers cannot bypass limits.
        sizes = sum(item.size_bytes for item in self.items)
        if sizes != self.total_bytes:
            raise ValueError("attachment total_bytes must equal the sum of item sizes")
        paths = tuple(item.resolved_path for item in self.items)
        if len(set(paths)) != len(paths):
            raise ValueError("attachment resolved paths must be unique")
        return self

    def manifest(self) -> tuple[dict[str, object], ...]:
        # Emits safe metadata only; attachment bodies never enter machine-facing manifests.
        return tuple(
            {
                "supplied_path": str(item.supplied_path),
                "resolved_path": str(item.resolved_path),
                "name": item.name,
                "kind": item.kind.value,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in self.items
        )


__all__ = ["AgentAttachment", "AttachmentBundle", "AttachmentKind"]
