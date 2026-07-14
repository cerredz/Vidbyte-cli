"""`vidbyte-cli connect github` — links GitHub so backend harnesses can clone and open PRs.

Unlike the other auth commands this is a linkage *flow* with a wait loop, not a single
request: it starts a server-side GitHub App/OAuth install, hands the user to the browser,
then polls until linked. The CLI never holds a GitHub token — it lives on the backend,
which is what actually clones repos and opens PRs.
"""

from __future__ import annotations

import click

from ...lib.errors.cli_error import not_implemented


class ConnectGithubCommand:
    def register(self, parent: click.Group) -> None:
        # Attaches `github` under the `connect` group.
        @parent.command(name="github", help="Connect your GitHub account for harness repo access")
        def _run() -> None:
            self.execute()

    def execute(self) -> None:
        # Will start the GitHub install flow, open the verification URL, and poll to linked.
        raise not_implemented("'vidbyte-cli connect github'")
