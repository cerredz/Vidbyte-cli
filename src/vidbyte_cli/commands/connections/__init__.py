"""Static commands for named GitHub, Slack, and Google Drive connections."""

from __future__ import annotations

import click

from .list import ConnectionListCommand
from .login import ConnectionLoginCommand
from .logout import ConnectionLogoutCommand
from .read import ConnectionReadCommand
from .status import ConnectionStatusCommand


class ConnectionsGroup:
    """Registers the local context-provider connection command family."""

    def register(self, parent: click.Group) -> None:
        # The group is static and side-effect free while the command tree is assembled.
        connections = click.Group(
            name="connections",
            help="Connect accounts and read bounded context-provider resources",
        )
        ConnectionLoginCommand().register(connections)
        ConnectionListCommand().register(connections)
        ConnectionStatusCommand().register(connections)
        ConnectionLogoutCommand().register(connections)
        ConnectionReadCommand().register(connections)
        parent.add_command(connections)
