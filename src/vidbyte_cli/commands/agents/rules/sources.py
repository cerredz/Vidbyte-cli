"""Free, credential-free verbs that show what a scan would read and under which limits.

`hosts` lists each supported host's transcript folder and what is in it, `sessions` lists the
sessions a scope selects, and `limits` prints every default and cap. None of them resolves an
API key, makes a request, or prints prompt text.
"""

from __future__ import annotations

import click

from ....lib.runtime.context import ApplicationContext
from ....services.rules.transcripts import TranscriptLibrary
from ....types.rules import RulesScanScope
from .options import RulesScopeOptions
from .render import RulesRenderer

_HOSTS_HELP = (
    "List every coding-agent host the rules agent can read, with the folder it reads each host's "
    "transcripts from. "
    "For each host it reports whether that folder exists, how many sessions are in it, and when "
    "the newest one was active. "
    "It reads only local files, needs no API key, and never prints prompt text or charges "
    "anything. "
    "Run it first when a scan finds no prompts, to see which hosts actually have transcripts on "
    "this machine."
)
_SESSIONS_HELP = (
    "List the sessions a scan with the same scope options would read, newest first, with each "
    "session's prompt count. "
    "It applies the host, date, project, and session filters exactly as the scan verb does, so "
    "the totals match what a scan would plan. "
    "It reads only local files, needs no API key, and never prints prompt text or charges "
    "anything. "
    "Use it to tune a scope before paying for it, for example to check that a project filter "
    "matches."
)
_LIMITS_HELP = (
    "Print the default value and the hard cap of every limit a rules scan runs under. "
    "It covers the time window, spend cap, per-batch cost cap, batch size, time limit, and "
    "session and prompt caps. "
    "It also prints the backend's own bounds, such as the maximum prompt length and the minimum "
    "balance a batch needs. "
    "It reads nothing, needs no API key, and charges nothing."
)


class RulesHostsCommand:
    """Registers and executes `agents rules hosts`."""

    def register(self, parent: click.Group) -> None:
        # A plain verb with no options.
        @parent.command(name="hosts", help=_HOSTS_HELP)
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Reads every host with no time window to count all saved sessions.
        library = TranscriptLibrary()
        counts: dict[str, tuple[int, str | None]] = {}
        for source in library.hosts():
            sessions = library.sessions(RulesScanScope(hosts=[source.host]))
            newest = (
                sessions[0].latest_at.isoformat(timespec="minutes")
                if sessions and sessions[0].latest_at
                else None
            )
            counts[source.host.value] = (len(sessions), newest)
        rendered = RulesRenderer().hosts(library.hosts(), counts)
        context.output().result(rendered.document, rendered.human)


class RulesSessionsCommand:
    """Registers and executes `agents rules sessions`."""

    def register(self, parent: click.Group) -> None:
        # Shares every scope option with the scan verb.
        def _run(context: ApplicationContext, /, **values: object) -> None:
            self.execute(context, values)

        parent.command(name="sessions", help=_SESSIONS_HELP)(
            RulesScopeOptions().apply(click.pass_obj(_run))
        )

    def execute(self, context: ApplicationContext, values: dict[str, object]) -> None:
        # Lists the sessions the scope selects, with prompt counts after the time window.
        sessions = TranscriptLibrary().sessions(RulesScopeOptions().build(values))
        rendered = RulesRenderer().sessions(sessions)
        context.output().result(rendered.document, rendered.human)


class RulesLimitsCommand:
    """Registers and executes `agents rules limits`."""

    def register(self, parent: click.Group) -> None:
        # A plain verb with no options.
        @parent.command(name="limits", help=_LIMITS_HELP)
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Prints static defaults and caps.
        rendered = RulesRenderer().limits()
        context.output().result(rendered.document, rendered.human)
