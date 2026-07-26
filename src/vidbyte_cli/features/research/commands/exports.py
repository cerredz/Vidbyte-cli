"""FILE: src/vidbyte_cli/features/research/commands/exports.py

PURPOSE: Declares artifact, thread, portfolio, and status commands for integration exports.

ROLE IN CODEBASE: Commands build strict ResearchExportRequest values and delegate job
submission/retrieval to ResearchExportService.

ARCHITECTURE NOTE: Provider names remain server-capability data rather than a hard-coded
Click choice. The final gateway performs capability validation before mutation.

TESTS: No feature tests are added under the approved no-tests workflow. PR 6 smoke covers
every export help path.
"""

from __future__ import annotations

import click
from pydantic import ValidationError

from ....lib.runtime.context import ApplicationContext
from ..domain import ExportScope, ResearchExportRequest
from ..presentation import ResearchPresenter
from .common import emit, raise_safe_validation


class ResearchExportArtifactsCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="artifact", help="Export one or more research artifacts")
        @click.argument("artifact_ids", nargs=-1, required=True)
        @click.option("--to", "provider", required=True, help="Configured integration provider.")
        @click.option("--idempotency-key", help="Reuse one logical export identity.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            artifact_ids: tuple[str, ...],
            provider: str,
            idempotency_key: str | None,
        ) -> None:
            request = self._request(provider, artifact_ids)
            value = context.research_export_service().create(request, idempotency_key)
            emit(context, ResearchPresenter().export(value))

    def _request(
        self,
        provider: str,
        artifact_ids: tuple[str, ...],
    ) -> ResearchExportRequest:
        try:
            return ResearchExportRequest(
                provider=provider,
                scope=ExportScope.ARTIFACTS,
                artifact_ids=list(artifact_ids),
            )
        except ValidationError as error:
            raise_safe_validation(error)


class ResearchExportThreadCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="thread", help="Export one complete research thread")
        @click.argument("thread_id")
        @click.option("--to", "provider", required=True, help="Configured integration provider.")
        @click.option("--idempotency-key", help="Reuse one logical export identity.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            thread_id: str,
            provider: str,
            idempotency_key: str | None,
        ) -> None:
            try:
                request = ResearchExportRequest(
                    provider=provider,
                    scope=ExportScope.THREAD,
                    thread_id=thread_id,
                )
            except ValidationError as error:
                raise_safe_validation(error)
            value = context.research_export_service().create(request, idempotency_key)
            emit(context, ResearchPresenter().export(value))


class ResearchExportPortfolioCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="portfolio", help="Export the complete research portfolio")
        @click.option("--to", "provider", required=True, help="Configured integration provider.")
        @click.option("--idempotency-key", help="Reuse one logical export identity.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            provider: str,
            idempotency_key: str | None,
        ) -> None:
            try:
                request = ResearchExportRequest(
                    provider=provider,
                    scope=ExportScope.PORTFOLIO,
                )
            except ValidationError as error:
                raise_safe_validation(error)
            value = context.research_export_service().create(request, idempotency_key)
            emit(context, ResearchPresenter().export(value))


class ResearchExportStatusCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="status", help="Show one research export job")
        @click.argument("export_id")
        @click.pass_obj
        def _run(context: ApplicationContext, export_id: str) -> None:
            value = context.research_export_service().get(export_id)
            emit(context, ResearchPresenter().export(value))
