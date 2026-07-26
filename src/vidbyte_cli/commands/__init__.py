"""FILE: src/vidbyte_cli/commands/__init__.py

PURPOSE: Registers the CLI's stable, locally known command groups and returns the generic
harness group where one dynamic namespace can be attached. This file owns command-tree
shape only; command execution and dynamic manifest resolution live elsewhere.

ROLE IN CODEBASE: lib/runtime/application.py calls register_all_commands() after creating
the root Click group. Individual command classes supply their adapters, while the runtime's
HarnessRegistry attaches a requested per-harness subtree to the returned group.

ARCHITECTURE NOTE: This is the static half of the accepted static/dynamic registration seam
documented in docs/architecture.md and docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- register_all_commands(program) -> click.Group: attaches stable groups and returns harness.

COMMON MODIFICATION PATTERNS: Add a stable cross-product command by importing its adapter
and registering it in the appropriate group. Product-specific command trees should expose
their own registration function rather than growing this file with business details.

WHAT NOT TO DO IN THIS FILE:
1. Do not perform credentials, filesystem, repository, or network work during registration.
2. Do not execute command use cases; command classes and services own behavior.
3. Do not load dynamic manifests; lib/runtime/application.py owns the second pass.
4. Do not call sys.exit or write to process streams.

KNOWN EDGE CASES: Registration runs for help and version paths, so every constructor called
here must remain side-effect free.

RELATED DOCS: https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md
explains the two-pass harness seam and static command registration boundary.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py renders representative groups and a static harness subtree.
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
    # Register stable groups without constructing optional runtime services or doing I/O.
    LoginCommand().register(program)
    LogoutCommand().register(program)
    WhoamiCommand().register(program)
    DoctorCommand().register(program)
    _register_connect_group(program)
    harness = _register_harness_group(program)
    _register_config_group(program)
    return harness


def _register_connect_group(program: click.Group) -> None:
    # External account commands share one stable namespace at the root.
    connect = click.Group(name="connect", help="Connect external accounts to Vidbyte")
    ConnectGithubCommand().register(connect)
    program.add_command(connect)


def _register_harness_group(program: click.Group) -> click.Group:
    # Generic harness verbs remain available before any dynamic namespace is resolved.
    harness = click.Group(name="harness", help="Run and inspect Vidbyte harnesses")
    HarnessRunCommand().register(harness)
    HarnessStatusCommand().register(harness)
    HarnessListCommand().register(harness)
    HarnessCatalogCommand().register(harness)
    program.add_command(harness)
    return harness


def _register_config_group(program: click.Group) -> None:
    # Configuration commands share one stable namespace at the root.
    config = click.Group(name="config", help="Manage CLI configuration")
    ConfigGetCommand().register(config)
    ConfigSetCommand().register(config)
    program.add_command(config)
