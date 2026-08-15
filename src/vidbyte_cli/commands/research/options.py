"""The request-shaping options `research start` and `research add` both accept.

Declared once because the two commands submit the identical body to different routes, and a
flag that drifted between them would be a silent behaviour difference nobody could see from
either file.

Only options the backend can act on are exposed. `source_sites` and `reference_artifact_ids`
exist on the request DTO but need a catalogue and an artifact list the API-key surface does
not publish, so a flag for either would accept values a caller has no way to discover.

Click hands a callback its parameters as loose values, so the readers below are where those
become typed: each one narrows a single option and the model rejects anything still wrong.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import click

from ...types.research import (
    IdempotencyKey,
    ResearchKind,
    ResearchRunCreateRequest,
    ResearchSize,
)

CommandCallback = Callable[..., None]
OptionDecorator = Callable[[CommandCallback], CommandCallback]


class ResearchRunOptions:
    """Declares the shared run options and turns the parsed values into a request."""

    def apply(self, callback: CommandCallback) -> CommandCallback:
        # Click decorators apply bottom-up, so this reverses them to match the help listing.
        for decorate in reversed(self._decorators()):
            callback = decorate(callback)
        return callback

    def build(self, values: Mapping[str, object]) -> ResearchRunCreateRequest:
        # Unset options stay None so the encoder omits them and the backend owns its defaults.
        return ResearchRunCreateRequest(
            prompt=self._prompt(values),
            size=self._size(values),
            target_sources=self._count(values, "target_sources"),
            search_calls=self._count(values, "search_calls"),
            resource_kinds=self._kinds(values),
            include_domains=self._many(values, "include_domain"),
            exclude_domains=self._many(values, "exclude_domain"),
            published_after=self._text(values, "published_after"),
            language=self._text(values, "language"),
            max_run_cost_cents=self._count(values, "max_cost_cents"),
        )

    def key(self, values: Mapping[str, object]) -> IdempotencyKey:
        # Validated before the request is built, so a bad key never reaches the network.
        return IdempotencyKey.create(self._text(values, "idempotency_key"))

    def _decorators(self) -> tuple[OptionDecorator, ...]:
        return (
            click.option(
                "--size",
                type=click.Choice([item.value for item in ResearchSize]),
                help="Preset run breadth, when not sizing the run by hand.",
            ),
            click.option(
                "--target-sources",
                type=click.IntRange(1, 1_000),
                help="How many sources discovery should aim to collect.",
            ),
            click.option(
                "--search-calls",
                type=click.IntRange(1, 100),
                help="Upper bound on provider search calls for this run.",
            ),
            click.option(
                "--kind",
                multiple=True,
                type=click.Choice([item.value for item in ResearchKind]),
                help="Restrict discovery to this resource kind. Repeatable.",
            ),
            click.option(
                "--include-domain",
                multiple=True,
                help="Restrict discovery to this hostname. Repeatable.",
            ),
            click.option(
                "--exclude-domain",
                multiple=True,
                help="Exclude this hostname from discovery. Repeatable.",
            ),
            click.option(
                "--published-after",
                help="Only consider sources published on or after this YYYY-MM-DD date.",
            ),
            click.option("--language", help="Preferred source language tag, such as 'en'."),
            click.option(
                "--max-cost-cents",
                type=click.IntRange(1, 100_000),
                help="Refuse the run if it would cost more than this many cents.",
            ),
            click.option(
                "--idempotency-key",
                help="Reuse a key to retry a priced mutation without being charged twice.",
            ),
        )

    def _prompt(self, values: Mapping[str, object]) -> str:
        # A required Click argument is always present; the model rejects a blank one.
        return str(values.get("prompt", ""))

    def _text(self, values: Mapping[str, object], name: str) -> str | None:
        value = values.get(name)
        return str(value) if isinstance(value, str) and value else None

    def _count(self, values: Mapping[str, object], name: str) -> int | None:
        value = values.get(name)
        return value if isinstance(value, int) else None

    def _many(self, values: Mapping[str, object], name: str) -> list[str] | None:
        # A repeatable option arrives as an empty tuple when unused, which must stay absent.
        value = values.get(name)
        if not isinstance(value, tuple) or not value:
            return None
        return [str(item) for item in value]

    def _size(self, values: Mapping[str, object]) -> ResearchSize | None:
        value = self._text(values, "size")
        return ResearchSize(value) if value is not None else None

    def _kinds(self, values: Mapping[str, object]) -> list[ResearchKind] | None:
        value = self._many(values, "kind")
        return [ResearchKind(item) for item in value] if value is not None else None
