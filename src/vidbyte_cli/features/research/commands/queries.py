"""FILE: src/vidbyte_cli/features/research/commands/queries.py

PURPOSE: Declares status, watch, cursor-list, artifact-read, and capability commands for
durable research resources.

ROLE IN CODEBASE: Query callbacks contain no transport logic. They call query/watcher
application services and use ResearchPresenter for both human and machine contracts.

ARCHITECTURE NOTE: Watch reports only coarse run transitions. Detailed internal agent event
logs remain a web-only product surface.

TESTS: No feature tests are added under the approved no-tests workflow. PR 6 smoke covers
all nested help paths without credentials or network access.
"""

from __future__ import annotations

from pathlib import Path

import click

from ....lib.runtime.context import ApplicationContext
from ..presentation import ResearchPresenter
from .common import apply_outcome_exit, emit


class ResearchStatusCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="status", help="Show one research run snapshot")
        @click.argument("run_id")
        @click.option(
            "--exit-status/--no-exit-status",
            default=False,
            help="Return a nonzero status for partial or unsuccessful terminal outcomes.",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, run_id: str, exit_status: bool) -> None:
            run = context.research_query_service().status(run_id)
            emit(context, ResearchPresenter().run(run))
            apply_outcome_exit(context, run.status, requested=exit_status)


class ResearchWatchCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="watch", help="Watch coarse progress for one research run")
        @click.argument("run_id")
        @click.option(
            "--timeout",
            type=click.FloatRange(min=1.0, max=86_400.0),
            default=None,
            help="Maximum local wait; the remote run continues after timeout.",
        )
        @click.option(
            "--exit-status/--no-exit-status",
            default=False,
            help="Return a nonzero status for partial or unsuccessful terminal outcomes.",
        )
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            run_id: str,
            timeout: float | None,
            exit_status: bool,
        ) -> None:
            run = context.research_watcher().watch(run_id, timeout)
            emit(context, ResearchPresenter().run(run))
            apply_outcome_exit(context, run.status, requested=exit_status)


class ResearchRunsListCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="list", help="List research runs")
        @click.option("--cursor", help="Continue from an opaque server cursor.")
        @click.pass_obj
        def _run(context: ApplicationContext, cursor: str | None) -> None:
            page = context.research_query_service().runs(cursor)
            emit(context, ResearchPresenter().runs(page))


class ResearchThreadsListCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="list", help="List persistent research threads")
        @click.option("--cursor", help="Continue from an opaque server cursor.")
        @click.pass_obj
        def _run(context: ApplicationContext, cursor: str | None) -> None:
            page = context.research_query_service().threads(cursor)
            emit(context, ResearchPresenter().threads(page))


class ResearchSourcesListCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="list", help="List sources stored in a research thread")
        @click.option("--thread", "thread_id", required=True, help="Opaque research thread ID.")
        @click.option("--cursor", help="Continue from an opaque server cursor.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            thread_id: str,
            cursor: str | None,
        ) -> None:
            page = context.research_query_service().sources(thread_id, cursor)
            emit(context, ResearchPresenter().sources(page))


class ResearchArtifactsListCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="list", help="List artifacts stored in a research thread")
        @click.option("--thread", "thread_id", required=True, help="Opaque research thread ID.")
        @click.option("--cursor", help="Continue from an opaque server cursor.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            thread_id: str,
            cursor: str | None,
        ) -> None:
            page = context.research_query_service().artifacts(thread_id, cursor)
            emit(context, ResearchPresenter().artifacts(page))


class ResearchArtifactGetCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="get", help="Get one research artifact")
        @click.argument("artifact_id")
        @click.option(
            "--output",
            type=click.Path(path_type=Path, dir_okay=False),
            help="Write the complete artifact to an explicit file.",
        )
        @click.option("--force", is_flag=True, help="Replace an existing --output file.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            artifact_id: str,
            output: Path | None,
            force: bool,
        ) -> None:
            artifact = context.research_query_service().artifact(artifact_id)
            emit(
                context,
                ResearchPresenter().artifact(artifact, output, force=force),
            )


class ResearchCapabilitiesCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="capabilities", help="Show server research and export capabilities")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            value = context.research_query_service().capabilities()
            emit(context, ResearchPresenter().capabilities(value))
