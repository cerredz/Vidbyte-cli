"""Reusable Click options for future commands that invoke local agents.

The option declaration stays separate from attachment resolution so command parsing remains
cheap and the same validated bundle can be reused by every future agent service.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

import click

from ..lib.io.attachments import AttachmentResolver
from ..types.attachments import AttachmentBundle

CommandCallback = Callable[..., None]
OptionDecorator = Callable[[CommandCallback], CommandCallback]

_ATTACH_HELP = (
    "Attach one explicit local file as context for the future agent invocation. "
    "Repeat this option once per file; occurrence order is preserved in the resolved bundle. "
    "Text files are captured as UTF-8 snapshots and supported images remain native "
    "local-image inputs. "
    "Missing, duplicate, empty, unsupported, or oversized files fail before credentials, "
    "payment, or model execution."
)


class AgentAttachmentOptions:
    """Declares and resolves the shared repeatable `--attach PATH` option."""

    def apply(self, callback: CommandCallback) -> CommandCallback:
        # Keeps Click syntax in commands while delegating all validation to the shared resolver.
        return click.option(
            "--attach",
            "attachments",
            multiple=True,
            type=click.Path(path_type=Path),
            help=_ATTACH_HELP,
        )(callback)

    def resolve(self, values: Mapping[str, object]) -> AttachmentBundle:
        # Extracts Click's tuple value and resolves it exactly once for the invocation.
        raw = values.get("attachments", ())
        if not isinstance(raw, tuple) or any(not isinstance(path, Path) for path in raw):
            from ..lib.errors.failures import AttachmentInputInvalid

            raise AttachmentInputInvalid()
        return AttachmentResolver().resolve(raw)


__all__ = ["AgentAttachmentOptions"]
