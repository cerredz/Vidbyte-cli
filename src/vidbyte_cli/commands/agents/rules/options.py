"""Scope and limit options shared by the rules agent's verbs, and their parsing.

Every value is validated here, before a transcript is read, a credential is resolved, or a cent
is spent, and a bad value raises `RulesInputInvalid` naming the option and its accepted shape.
Durations look like `30d`, `12h`, `45m`, or `90s`; a point in time may also be an ISO date or
date-time; money is written in dollars such as `2.50` and stored in whole cents.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import click

from ....lib.constants.rules import RULES_DEFAULT_SINCE, RulesBackendLimit, RulesCap, RulesDefault
from ....lib.errors.failures import RulesInputInvalid
from ....types.rules import RulesHost, RulesScanLimits, RulesScanScope

_DURATION = re.compile(r"^(\d+)\s*([dhms])$", re.IGNORECASE)
_UNIT_SECONDS = {"d": 86_400, "h": 3_600, "m": 60, "s": 1}
_CENTS_PER_DOLLAR = Decimal(100)

HOST_HELP = (
    "Read prompts only from this coding-agent host, and repeat the flag to include several hosts. "
    "The supported hosts are claude, codex, grok, and opencode, which read Claude Code, Codex, "
    "Grok "
    "Build, and OpenCode transcripts respectively. When the flag is omitted every supported host "
    "is "
    "read, and a host whose transcript folder does not exist simply contributes nothing. Run the "
    "hosts verb first to see which folders exist on this machine."
)
SINCE_HELP = (
    "Include only prompts written at or after this point in time. Give a duration counted back "
    "from now, such as 30d, 12h, or 45m, or an ISO date or date-time such as 2026-09-01. The "
    f"default is {RULES_DEFAULT_SINCE}, which keeps a first scan small and cheap while still "
    "covering "
    "a month of work. Files older than this point are skipped without being parsed."
)
UNTIL_HELP = (
    "Include only prompts written at or before this point in time. It accepts the same duration "
    "and ISO date forms as --since, so --until 7d ends the window one week ago. The default is "
    "now, "
    "which includes the most recent prompts on disk. Combine it with --since to scan one exact "
    "period, such as a single past sprint."
)
PROJECT_HELP = (
    "Include only sessions whose working directory is this folder or any folder beneath it. The "
    "comparison ignores letter case and slash direction, so Windows and POSIX spellings of one "
    "path "
    "match each other. Sessions whose host did not record a working directory are left out when "
    "this flag is set. Omit the flag to scan sessions from every project."
)
MAX_SESSIONS_HELP = (
    "Keep at most this many sessions, taking the most recently active sessions first. The cap is "
    "applied after the host, date, and project filters have narrowed the set. It is the simplest "
    "way to bound a first scan when many sessions fall inside the window. Omit it to keep every "
    "session that matches the other filters."
)
MAX_PROMPTS_HELP = (
    "Send at most this many prompts in total, taken from the most recent sessions first. The cap "
    "applies after session selection, so it can cut the oldest selected session short. It directly "
    "bounds how many prompts Jev classifies and therefore the largest part of the cost. Omit it to "
    "send every prompt the other filters selected."
)
MAX_SPEND_HELP = (
    "Stop the scan before it spends more than this many dollars in total, for example 2.50. The "
    "cap counts the metered charge every finished batch reported, including batches from earlier "
    "runs of the same scan. A scan stops before any batch whose remaining budget is below the "
    f"backend's minimum, and the default is ${RulesDefault.MAX_SPEND_CENTS / 100:.2f}."
)
MAX_BATCH_COST_HELP = (
    "Cap what any single batch may spend, in dollars, for example 0.50. The backend enforces this "
    "cap while the batch runs, so a batch that would cost more stops instead of overspending. The "
    "value used for each batch is the smaller of this cap and the scan's remaining budget. The "
    f"default is ${RulesDefault.MAX_BATCH_COST_CENTS / 100:.2f}, and the backend allows at most "
    f"${RulesBackendLimit.MAX_BATCH_COST_CENTS / 100:.2f}."
)
TIME_LIMIT_HELP = (
    "Stop sending new batches once this much wall-clock time has passed, such as 20m or 1h. A "
    "batch "
    "already in flight is allowed to finish, so the scan never pays for work it then discards. The "
    "stopped scan keeps its progress and can be continued later with the resume verb. Omit the "
    "flag "
    "to let the scan run until its batches or its budget run out."
)
BATCH_SIZE_HELP = (
    "Send this many prompts in each paid batch request, between 1 and "
    f"{RulesBackendLimit.BATCH_MAX_PROMPTS}. Larger batches mean fewer requests and fewer minimum "
    "balance checks, while smaller batches make the spend and time limits more precise. Each batch "
    "is recorded as soon as it finishes, so a failure loses at most one batch of work. The default "
    f"is {RulesDefault.BATCH_SIZE}."
)


class DurationParser:
    """Turns duration or ISO time strings into aware UTC datetimes and seconds."""

    def point_in_time(self, option: str, raw: str) -> datetime:
        # A duration counts back from now; anything else must parse as an ISO date or date-time.
        seconds = self._duration_seconds(raw)
        if seconds is not None:
            return datetime.now(UTC) - timedelta(seconds=seconds)
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise RulesInputInvalid(
                option, "a duration such as 30d, 12h, or 45m, or an ISO date such as 2026-09-01"
            ) from error
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def seconds(self, option: str, raw: str) -> int:
        # A positive duration in whole seconds.
        seconds = self._duration_seconds(raw)
        if seconds is None or seconds < 1:
            raise RulesInputInvalid(option, "a positive duration such as 20m, 1h, or 90s")
        return seconds

    @staticmethod
    def _duration_seconds(raw: str) -> int | None:
        # None when the text is not a duration at all.
        match = _DURATION.match(raw.strip())
        return int(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()] if match else None


class MoneyParser:
    """Turns dollar strings into whole cents."""

    @staticmethod
    def cents(option: str, raw: str, *, maximum: int) -> int:
        # Rounds to the nearest cent and rejects values below one cent or above the cap.
        try:
            cents = int((Decimal(raw.strip().lstrip("$")) * _CENTS_PER_DOLLAR).quantize(Decimal(1)))
        except (InvalidOperation, ValueError) as error:
            raise RulesInputInvalid(option, "a dollar amount such as 2.50") from error
        if not 1 <= cents <= maximum:
            raise RulesInputInvalid(option, f"an amount between $0.01 and ${maximum / 100:.2f}")
        return cents


class RulesScopeOptions:
    """Attaches and parses the options that decide which transcripts are read."""

    def apply(self, callback: Callable[..., None]) -> Callable[..., None]:
        # Decorates a Click callback with every scope option, in help order.
        decorators = [
            click.option(
                "--max-prompts",
                type=click.IntRange(1, RulesCap.MAX_PROMPTS),
                default=None,
                help=MAX_PROMPTS_HELP,
            ),
            click.option(
                "--max-sessions",
                type=click.IntRange(1, RulesCap.MAX_SESSIONS),
                default=None,
                help=MAX_SESSIONS_HELP,
            ),
            click.option("--project", type=str, default=None, help=PROJECT_HELP),
            click.option("--until", "until_text", type=str, default=None, help=UNTIL_HELP),
            click.option(
                "--since",
                "since_text",
                type=str,
                default=RULES_DEFAULT_SINCE,
                show_default=True,
                help=SINCE_HELP,
            ),
            click.option(
                "--host",
                "hosts",
                type=click.Choice([host.value for host in RulesHost]),
                multiple=True,
                help=HOST_HELP,
            ),
        ]
        for decorator in decorators:
            callback = decorator(callback)
        return callback

    def build(self, values: dict[str, object]) -> RulesScanScope:
        # Resolves relative times now, so the stored scope means the same thing on resume.
        parser = DurationParser()
        since_text = values.get("since_text")
        until_text = values.get("until_text")
        since = parser.point_in_time("--since", str(since_text)) if since_text else None
        until = parser.point_in_time("--until", str(until_text)) if until_text else None
        if since is not None and until is not None and since > until:
            raise RulesInputInvalid("--since", "a point in time earlier than --until")
        raw_hosts = values.get("hosts")
        chosen = raw_hosts if isinstance(raw_hosts, (tuple, list)) else ()
        hosts = [RulesHost(str(host)) for host in chosen] or list(RulesHost)
        project = values.get("project")
        return RulesScanScope(
            hosts=list(dict.fromkeys(hosts)),
            since=since,
            until=until,
            project=str(project) if project else None,
            max_sessions=self._optional_int(values.get("max_sessions")),
            max_prompts=self._optional_int(values.get("max_prompts")),
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        # Click already range-checked the value; this only narrows the type.
        return int(value) if isinstance(value, int) else None


class RulesLimitOptions:
    """Attaches and parses the options that bound spend, time, and batching."""

    def apply(self, callback: Callable[..., None]) -> Callable[..., None]:
        # Decorates a Click callback with every limit option, in help order.
        decorators = [
            click.option(
                "--batch-size",
                type=click.IntRange(1, RulesBackendLimit.BATCH_MAX_PROMPTS),
                default=RulesDefault.BATCH_SIZE,
                show_default=True,
                help=BATCH_SIZE_HELP,
            ),
            click.option(
                "--time-limit", "time_limit_text", type=str, default=None, help=TIME_LIMIT_HELP
            ),
            click.option(
                "--max-batch-cost",
                "max_batch_cost_text",
                type=str,
                default=f"{RulesDefault.MAX_BATCH_COST_CENTS / 100:.2f}",
                show_default=True,
                help=MAX_BATCH_COST_HELP,
            ),
            click.option(
                "--max-spend",
                "max_spend_text",
                type=str,
                default=f"{RulesDefault.MAX_SPEND_CENTS / 100:.2f}",
                show_default=True,
                help=MAX_SPEND_HELP,
            ),
        ]
        for decorator in decorators:
            callback = decorator(callback)
        return callback

    def build(self, values: dict[str, object]) -> RulesScanLimits:
        # Converts dollars to cents and durations to seconds, rejecting anything out of range.
        time_text = values.get("time_limit_text")
        seconds = DurationParser().seconds("--time-limit", str(time_text)) if time_text else None
        if seconds is not None and seconds > RulesCap.TIME_LIMIT_SECONDS:
            raise RulesInputInvalid("--time-limit", "a duration of at most 24h")
        return RulesScanLimits(
            max_spend_cents=MoneyParser.cents(
                "--max-spend", str(values.get("max_spend_text")), maximum=RulesCap.MAX_SPEND_CENTS
            ),
            max_batch_cost_cents=MoneyParser.cents(
                "--max-batch-cost",
                str(values.get("max_batch_cost_text")),
                maximum=RulesBackendLimit.MAX_BATCH_COST_CENTS,
            ),
            batch_size=int(str(values.get("batch_size") or RulesDefault.BATCH_SIZE)),
            time_limit_seconds=seconds,
        )
