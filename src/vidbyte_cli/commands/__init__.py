"""Single registration point for the CLI's *static* command surface.

This is the static half of the static/dynamic seam (commands/index.ts:23 review comment):
the platform commands and the generic harness verbs (`run`, `status`, `list`, `catalog`)
register here synchronously. Per-harness command subtrees are NOT built here — they depend
on a manifest that arrives over the network, and are attached in a second pass by cli.py via
the harness factory. Keep this file the home of the stable surface only.
"""

from __future__ import annotations

import click

from .auth.connect_github import ConnectGithubCommand
from .auth.login import LoginCommand
from .auth.logout import LogoutCommand
from .auth.whoami import WhoamiCommand
from .config.get import ConfigGetCommand
from .config.set import ConfigSetCommand
from .harness.catalog import HarnessCatalogCommand
from .harness.list import HarnessListCommand
from .harness.run import HarnessRunCommand
from .harness.status import HarnessStatusCommand
from .setup.doctor import DoctorCommand


def register_all_commands(program: click.Group) -> click.Group:
    # Attaches every static command group to the root program. Returns the `harness` group so
    # cli.py can attach a dynamic harness subtree onto it in the second pass.
    LoginCommand().register(program)
    LogoutCommand().register(program)
    WhoamiCommand().register(program)
    DoctorCommand().register(program)

    connect = click.Group(name="connect", help="Connect external accounts to Vidbyte")
    ConnectGithubCommand().register(connect)
    program.add_command(connect)

    harness = click.Group(name="harness", help="Run and inspect Vidbyte harnesses")
    HarnessRunCommand().register(harness)
    HarnessStatusCommand().register(harness)
    HarnessListCommand().register(harness)
    HarnessCatalogCommand().register(harness)
    program.add_command(harness)

    config = click.Group(name="config", help="Manage CLI configuration")
    ConfigGetCommand().register(config)
    ConfigSetCommand().register(config)
    program.add_command(config)

    return harness
