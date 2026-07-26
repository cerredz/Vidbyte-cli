"""FILE: src/vidbyte_cli/features/research/commands/common.py

PURPOSE: Shares Click option declarations and command-boundary translation for research
mutation inputs without leaking Click into domain or application code.

ROLE IN CODEBASE: Start and add use the same request options and prompt-source resolver.
All research commands use emit() and optional terminal-outcome exit policy.

ARCHITECTURE NOTE: Validation errors are converted to safe field-oriented usage errors;
prompt values and Pydantic input representations never enter diagnostics.

TESTS: No feature tests are added under the approved no-tests workflow. The command-help
smoke cases parse every shared option declaration.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import NoReturn, TypeVar

import click
from pydantic import ValidationError

from ....lib.errors import usage_error
from ....lib.io import PromptInputResolver
from ....lib.runtime.context import ApplicationContext
from ..application import ResearchMutationInput
from ..domain import ResearchRunRequest, ResearchSize, ResearchStatus, ResourceKind
from ..domain.status import ResearchStatePolicy
from ..presentation import PresentedResult

_CommandFunction = TypeVar("_CommandFunction", bound=Callable[..., object])


def research_request_options(function: _CommandFunction) -> _CommandFunction:
    """Apply the canonical research request options to one Click callback."""
    function = click.option(
        "--language",
        help="Prefer a BCP-47-style content language such as en or en-US.",
    )(function)
    function = click.option(
        "--published-after",
        type=click.DateTime(formats=["%Y-%m-%d"]),
        help="Only include resources published after YYYY-MM-DD.",
    )(function)
    function = click.option(
        "--exclude-domain",
        "exclude_domains",
        multiple=True,
        help="Exclude a domain; repeat for multiple domains.",
    )(function)
    function = click.option(
        "--include-domain",
        "include_domains",
        multiple=True,
        help="Restrict search to a domain; repeat for multiple domains.",
    )(function)
    function = click.option(
        "--resource-kind",
        "resource_kinds",
        type=click.Choice([item.value for item in ResourceKind], case_sensitive=False),
        multiple=True,
        help="Include a resource kind; repeat for multiple kinds.",
    )(function)
    function = click.option(
        "--search-calls",
        type=click.IntRange(min=1, max=100),
        help="Maximum provider searches.",
    )(function)
    function = click.option(
        "--target-sources",
        type=click.IntRange(min=1, max=1_000),
        help="Requested source outcome.",
    )(function)
    function = click.option(
        "--size",
        type=click.Choice([item.value for item in ResearchSize], case_sensitive=False),
        default=ResearchSize.SMALL.value,
        show_default=True,
    )(function)
    function = click.option(
        "--prompt-file",
        type=click.Path(exists=True, dir_okay=False, path_type=str),
        help="Read the prompt from one UTF-8 file.",
    )(function)
    return function


def mutation_control_options(function: _CommandFunction) -> _CommandFunction:
    """Apply idempotency, wait, timeout, and outcome-exit controls."""
    function = click.option(
        "--exit-status/--no-exit-status",
        default=False,
        help="Return a nonzero status for partial or unsuccessful terminal outcomes.",
    )(function)
    function = click.option(
        "--timeout",
        type=click.FloatRange(min=1.0, max=86_400.0),
        default=None,
        help="Maximum local wait in seconds; the remote run continues after timeout.",
    )(function)
    function = click.option("--wait/--no-wait", default=True, show_default=True)(function)
    function = click.option(
        "--idempotency-key",
        help="Reuse one logical mutation identity after an uncertain result.",
    )(function)
    return function


def build_mutation_input(
    context: ApplicationContext,
    *,
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
) -> ResearchMutationInput:
    """Resolve one prompt source and create the strict application input."""
    resolved_prompt = PromptInputResolver(context.streams).resolve(prompt, prompt_file)
    try:
        request = ResearchRunRequest(
            prompt=resolved_prompt,
            size=ResearchSize(size),
            target_sources=target_sources,
            search_calls=search_calls,
            resource_kinds=[ResourceKind(item) for item in resource_kinds],
            include_domains=list(include_domains),
            exclude_domains=list(exclude_domains),
            published_after=published_after.date() if published_after is not None else None,
            language=language,
        )
        return ResearchMutationInput(
            request=request,
            idempotency_key=idempotency_key,
            wait=wait,
            timeout_seconds=timeout,
        )
    except (ValidationError, ValueError) as error:
        raise_safe_validation(error)


def emit(context: ApplicationContext, result: PresentedResult) -> None:
    context.output().result(result.document, result.human)


def apply_outcome_exit(
    context: ApplicationContext,
    status: ResearchStatus,
    *,
    requested: bool,
) -> None:
    if requested:
        policy = ResearchStatePolicy()
        if policy.is_terminal(status):
            context.set_exit_code(int(policy.exit_code(status)))


def raise_safe_validation(error: ValidationError | ValueError) -> NoReturn:
    """Map model failures without displaying input values or raw validation internals."""
    field = "research options"
    if isinstance(error, ValidationError) and error.errors(include_input=False):
        location = error.errors(include_input=False)[0].get("loc", ())
        if location:
            field = ".".join(str(item) for item in location)
    raise usage_error(
        f"Invalid value for {field}.",
        "Review the command options and run --help for accepted values.",
    ) from error
