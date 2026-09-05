"""Single registration point for the CLI's whole command surface.

Every command is static and known at release time — there is no manifest-driven or otherwise
dynamic subtree, so this file is the complete list of what `--help` can show. A command
belongs here only when a shipped backend route can answer it.

Registration must stay side-effect free: every help and version invocation executes it.
"""

from __future__ import annotations

import click

from .auth.login import LoginCommand
from .auth.logout import LogoutCommand
from .auth.whoami import WhoamiCommand
from .config.get import ConfigGetCommand
from .config.set import ConfigSetCommand
from .research.add import ResearchAddCommand
from .research.resume import ResearchResumeCommand
from .research.start import ResearchStartCommand
from .research.status import ResearchStatusCommand
from .research.thread import ResearchThreadCommand
from .research.threads import ResearchThreadsCommand
from .research.watch import ResearchWatchCommand
from .runtime import (
    AdversarialTeamCommand,
    PersistenceCommand,
    RuntimeDoctorCommand,
    RuntimeListCommand,
)
from .setup.doctor import DoctorCommand


def register_all_commands(program: click.Group) -> None:
    # Attaches every command group to the root program; the surface is entirely static.
    LoginCommand().register(program)
    LogoutCommand().register(program)
    WhoamiCommand().register(program)
    DoctorCommand().register(program)

    # The whole public API-key research surface: start, add, resume, read, watch, list.
    research = click.Group(name="research", help="Run and inspect Vidbyte research threads")
    ResearchStartCommand().register(research)
    ResearchAddCommand().register(research)
    ResearchResumeCommand().register(research)
    ResearchStatusCommand().register(research)
    ResearchWatchCommand().register(research)
    ResearchThreadsCommand().register(research)
    ResearchThreadCommand().register(research)
    program.add_command(research)

    runtime = click.Group(name="runtime", help="Run Vidbyte primitives on this machine")
    RuntimeListCommand().register(runtime)
    RuntimeDoctorCommand().register(runtime)
    AdversarialTeamCommand().register(runtime)
    PersistenceCommand().register(runtime)
    program.add_command(runtime)

    config = click.Group(name="config", help="Manage CLI configuration")
    ConfigGetCommand().register(config)
    ConfigSetCommand().register(config)
    program.add_command(config)
