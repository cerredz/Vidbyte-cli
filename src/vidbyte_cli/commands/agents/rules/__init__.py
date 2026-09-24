"""Registers the rules agent: turn past coding-agent prompts into one standing-rules document.

The group keeps the paid verbs (`scan`, `resume`) beside the free ones that inspect sources,
limits, and stored scans. Registration imports no service code, so every help path works
without credentials, transcripts, or network access.
"""

from __future__ import annotations

import click


class RulesAgentGroup:
    """Attaches scan, resume, hosts, sessions, limits, list, and show."""

    def register(self, parent: click.Group) -> None:
        # Builds the group here so commands/agents/__init__.py stays declarative.
        from .history import RulesListCommand, RulesShowCommand
        from .scan import RulesResumeCommand, RulesScanCommand
        from .sources import RulesHostsCommand, RulesLimitsCommand, RulesSessionsCommand

        rules = click.Group(name="rules", help=_RULES_HELP)
        for command in (
            RulesScanCommand(),
            RulesResumeCommand(),
            RulesHostsCommand(),
            RulesSessionsCommand(),
            RulesLimitsCommand(),
            RulesListCommand(),
            RulesShowCommand(),
        ):
            command.register(rules)
        parent.add_command(rules)


_RULES_HELP = (
    "The rules agent reads the prompts you typed into coding agents and writes the lasting "
    "preferences and corrections among them as standing rules. "
    "It reads Claude Code, Codex, Grok Build, and OpenCode transcripts from this machine and "
    "sends only the prompts you typed, in small paid batches. "
    "TypeSafe Jev flags the prompts that state a rule, a hosted agent writes the rules, and every "
    "batch is metered against your Vidbyte API wallet under limits you set. "
    "The result is one Markdown document you can read, keep, or paste into CLAUDE.md or AGENTS.md."
)
