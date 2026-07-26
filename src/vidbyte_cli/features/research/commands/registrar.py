"""FILE: src/vidbyte_cli/features/research/commands/registrar.py

PURPOSE: Builds the complete static research command tree without constructing services,
credentials, storage, or network clients.

ROLE IN CODEBASE: commands/register_all_commands calls this registrar with the invocation
environment. PR 7 enables the production tree by default while retaining an explicit
VIDBYTE_EXPERIMENTAL_RESEARCH=0 rollback switch.

ARCHITECTURE NOTE: Every group and command is attached synchronously. Merely rendering help
cannot resolve a research gateway or make an API request.

TESTS: No feature tests are added under the approved no-tests workflow. scripts/smoke.py
enables the gate and renders the complete nested tree.
"""

from __future__ import annotations

from collections.abc import Mapping

import click

from .exports import (
    ResearchExportArtifactsCommand,
    ResearchExportPortfolioCommand,
    ResearchExportStatusCommand,
    ResearchExportThreadCommand,
)
from .mutations import ResearchAddCommand, ResearchResumeCommand, ResearchStartCommand
from .queries import (
    ResearchArtifactGetCommand,
    ResearchArtifactsListCommand,
    ResearchCapabilitiesCommand,
    ResearchRunsListCommand,
    ResearchSourcesListCommand,
    ResearchStatusCommand,
    ResearchThreadsListCommand,
    ResearchWatchCommand,
)

_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})


class ResearchCommandRegistrar:
    """Side-effect-free builder for the feature-owned Click namespace."""

    def register(
        self,
        parent: click.Group,
        environment: Mapping[str, str],
    ) -> None:
        if not self._enabled(environment):
            return
        research = click.Group(
            name="research",
            help="Build and inspect persistent research portfolios",
        )
        ResearchStartCommand().register(research)
        ResearchAddCommand().register(research)
        ResearchResumeCommand().register(research)
        ResearchStatusCommand().register(research)
        ResearchWatchCommand().register(research)
        ResearchCapabilitiesCommand().register(research)
        self._register_queries(research)
        self._register_exports(research)
        parent.add_command(research)

    def _enabled(self, environment: Mapping[str, str]) -> bool:
        value = environment.get("VIDBYTE_EXPERIMENTAL_RESEARCH")
        return value is None or value.strip().lower() not in _DISABLED_VALUES

    def _register_queries(self, research: click.Group) -> None:
        runs = click.Group(name="runs", help="Inspect research runs")
        ResearchRunsListCommand().register(runs)
        research.add_command(runs)

        threads = click.Group(name="threads", help="Inspect persistent research threads")
        ResearchThreadsListCommand().register(threads)
        research.add_command(threads)

        sources = click.Group(name="sources", help="Inspect stored research sources")
        ResearchSourcesListCommand().register(sources)
        research.add_command(sources)

        artifacts = click.Group(name="artifacts", help="Inspect stored research artifacts")
        ResearchArtifactsListCommand().register(artifacts)
        ResearchArtifactGetCommand().register(artifacts)
        research.add_command(artifacts)

    def _register_exports(self, research: click.Group) -> None:
        exports = click.Group(name="export", help="Export research to an integration")
        ResearchExportArtifactsCommand().register(exports)
        ResearchExportThreadCommand().register(exports)
        ResearchExportPortfolioCommand().register(exports)
        ResearchExportStatusCommand().register(exports)
        research.add_command(exports)
