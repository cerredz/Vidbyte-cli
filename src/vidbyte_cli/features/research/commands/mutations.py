"""FILE: src/vidbyte_cli/features/research/commands/mutations.py

PURPOSE: Declares start, add, and resume commands for persistent research work.

ROLE IN CODEBASE: The callbacks translate Click values through common.py, invoke
ResearchService, and hand presentation to the shared output manager.

ARCHITECTURE NOTE: Resume accepts no prompt or request-shaping options. It can only continue
the durable state already associated with its opaque run ID.

TESTS: No feature tests are added under the approved no-tests workflow. PR 6 smoke covers
each help path and the adapter-disabled execution boundary.
"""

from __future__ import annotations

from datetime import datetime

import click

from ....lib.runtime.context import ApplicationContext
from ..application import ResearchResumeInput
from ..presentation import ResearchPresenter
from .common import (
    apply_outcome_exit,
    build_mutation_input,
    emit,
    mutation_control_options,
    research_request_options,
)


class ResearchStartCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="start", help="Start a persistent research thread")
        @click.argument("prompt", required=False)
        @research_request_options
        @mutation_control_options
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            prompt: str | None,
            prompt_file: str | None,
            size: str,
            target_sources: int | None,
            search_calls: int | None,
            resource_kinds: tuple[str, ...],
            include_domains: tuple[str, ...],
            exclude_domains: tuple[str, ...],
            published_after: datetime | None,
            language: str | None,
            idempotency_key: str | None,
            wait: bool,
            timeout: float | None,
            exit_status: bool,
        ) -> None:
            command = build_mutation_input(
                context,
                prompt=prompt,
                prompt_file=prompt_file,
                size=size,
                target_sources=target_sources,
                search_calls=search_calls,
                resource_kinds=resource_kinds,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                published_after=published_after,
                language=language,
                idempotency_key=idempotency_key,
                wait=wait,
                timeout=timeout,
            )
            result = context.research_service().start(command)
            emit(context, ResearchPresenter().mutation(result))
            if result.run is not None:
                apply_outcome_exit(context, result.run.status, requested=exit_status)


class ResearchAddCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="add", help="Add research work to an existing thread")
        @click.argument("thread_id")
        @click.argument("prompt", required=False)
        @research_request_options
        @mutation_control_options
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            thread_id: str,
            prompt: str | None,
            prompt_file: str | None,
            size: str,
            target_sources: int | None,
            search_calls: int | None,
            resource_kinds: tuple[str, ...],
            include_domains: tuple[str, ...],
            exclude_domains: tuple[str, ...],
            published_after: datetime | None,
            language: str | None,
            idempotency_key: str | None,
            wait: bool,
            timeout: float | None,
            exit_status: bool,
        ) -> None:
            command = build_mutation_input(
                context,
                prompt=prompt,
                prompt_file=prompt_file,
                size=size,
                target_sources=target_sources,
                search_calls=search_calls,
                resource_kinds=resource_kinds,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                published_after=published_after,
                language=language,
                idempotency_key=idempotency_key,
                wait=wait,
                timeout=timeout,
            )
            result = context.research_service().add(thread_id, command)
            emit(context, ResearchPresenter().mutation(result))
            if result.run is not None:
                apply_outcome_exit(context, result.run.status, requested=exit_status)


class ResearchResumeCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="resume", help="Continue a resumable research run")
        @click.argument("run_id")
        @mutation_control_options
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            run_id: str,
            idempotency_key: str | None,
            wait: bool,
            timeout: float | None,
            exit_status: bool,
        ) -> None:
            command = ResearchResumeInput(
                idempotency_key=idempotency_key,
                wait=wait,
                timeout_seconds=timeout,
            )
            result = context.research_service().resume(run_id, command)
            emit(context, ResearchPresenter().mutation(result))
            if result.run is not None:
                apply_outcome_exit(context, result.run.status, requested=exit_status)
