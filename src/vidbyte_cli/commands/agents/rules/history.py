"""Free verbs over stored rules scans: `list` past scans and `show` one scan's rules.

Both read only the local scan folders, need no API key, and charge nothing.
"""

from __future__ import annotations

import click

from ....lib.constants.rules import RulesDefault
from ....lib.runtime.context import ApplicationContext
from ....services.rules.store import RulesScanStore
from .render import RulesRenderer

_LIST_HELP = (
    "List the rules scans stored on this machine, newest first. "
    "Each row shows the scan ID, when it was created, whether it completed or stopped, how many "
    "batches finished, what it spent, and how many rules it wrote. "
    "Use the scan ID with the show verb to print a scan's rules, or with the resume verb to "
    "continue a stopped scan. "
    "It reads only local files, needs no API key, and charges nothing."
)
_LIST_LIMIT_HELP = (
    "Show at most this many scans, newest first. "
    f"The default is {RulesDefault.LIST_LIMIT}, which keeps the listing readable in a terminal. "
    "Raise it to find an older scan whose ID you no longer have. "
    "The limit changes only what is printed, never what is stored."
)
_SHOW_HELP = (
    "Print the rules document of the stored scan named by SCAN_ID. "
    "Human output is the Markdown document exactly as it was written to the scan folder, ready to "
    "paste into CLAUDE.md or AGENTS.md. "
    "JSON output instead returns the structured rules with their scope and evidence prompt IDs. "
    "It reads only local files, needs no API key, and charges nothing."
)


class RulesListCommand:
    """Registers and executes `agents rules list`."""

    def register(self, parent: click.Group) -> None:
        # One optional display limit.
        @parent.command(name="list", help=_LIST_HELP)
        @click.option(
            "--limit",
            type=click.IntRange(1, 1000),
            default=RulesDefault.LIST_LIMIT,
            show_default=True,
            help=_LIST_LIMIT_HELP,
        )
        @click.pass_obj
        def _run(context: ApplicationContext, limit: int) -> None:
            self.execute(context, limit)

    def execute(self, context: ApplicationContext, limit: int) -> None:
        # Stored scans, newest first, trimmed to the display limit.
        manifests = RulesScanStore(context.paths()).list_manifests()[:limit]
        rendered = RulesRenderer().scans(manifests)
        context.output().result(rendered.document, rendered.human)


class RulesShowCommand:
    """Registers and executes `agents rules show`."""

    def register(self, parent: click.Group) -> None:
        # SCAN_ID names the stored scan to print.
        @parent.command(name="show", help=_SHOW_HELP)
        @click.argument("scan_id")
        @click.pass_obj
        def _run(context: ApplicationContext, scan_id: str) -> None:
            self.execute(context, scan_id)

    def execute(self, context: ApplicationContext, scan_id: str) -> None:
        # The stored document for humans, the structured rules for machines.
        store = RulesScanStore(context.paths())
        manifest = store.load_manifest(scan_id)
        rules = [rule for record in store.load_batches(manifest) for rule in record.result.rules]
        rendered = RulesRenderer().show(manifest, store.read_document(scan_id), rules)
        context.output().result(rendered.document, rendered.human)
