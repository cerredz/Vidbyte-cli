"""FILE: src/vidbyte_cli/features/research/infrastructure/api_gateway.py

PURPOSE: Implements ResearchGateway over the Vidbyte public API with confirmed mutation
routes, assumed forward read routes, and strict direct DTO decoding.

ROLE IN CODEBASE: ApplicationContext lazily creates this adapter only when a research
command executes. Domain/application/command layers never import it.

ARCHITECTURE NOTE: Every POST receives the caller's one stable idempotency key. Continue
sends no prompt and no body. Route assumptions are isolated in routes.py, and provider-key
fields have no representation in the request DTO.

TESTS: No feature tests are added under the approved no-tests workflow. An HTTPX
MockTransport verification exercises exact methods, paths, bodies, headers, and mappings.
"""

from __future__ import annotations

from ....lib.api.client import ApiClient
from ....lib.api.response import ResponseShape
from ..domain import (
    Page,
    ResearchArtifact,
    ResearchGateway,
    ResearchRun,
    ResearchRunAccepted,
    ResearchRunRequest,
    ResearchSource,
    ResearchThread,
)
from .routes import ResearchRoutes
from .wire import (
    ApiResearchArtifact,
    ApiResearchPage,
    ApiResearchRun,
    ApiResearchRunAccepted,
    ApiResearchRunCreateRequest,
    ApiResearchSource,
    ApiResearchThread,
)


class ApiResearchGateway(ResearchGateway):
    """Concrete synchronous gateway for persistent research resources."""

    def __init__(
        self,
        client: ApiClient,
        routes: ResearchRoutes | None = None,
    ) -> None:
        self._client = client
        self._routes = routes or ResearchRoutes()

    def start(
        self,
        request: ResearchRunRequest,
        idempotency_key: str,
    ) -> ResearchRunAccepted:
        value = self._client.post(
            self._routes.CREATE_RUN,
            ApiResearchRunCreateRequest.from_domain(request),
            ApiResearchRunAccepted,
            idempotency_key=idempotency_key,
            shape=ResponseShape.DIRECT,
        )
        return value.to_domain()

    def add(
        self,
        thread_id: str,
        request: ResearchRunRequest,
        idempotency_key: str,
    ) -> ResearchRunAccepted:
        value = self._client.post(
            self._routes.append_run(thread_id),
            ApiResearchRunCreateRequest.from_domain(request),
            ApiResearchRunAccepted,
            idempotency_key=idempotency_key,
            shape=ResponseShape.DIRECT,
        )
        return value.to_domain()

    def resume(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted:
        # @intent continuation-preserves-original-request
        # The confirmed backend route has no request body; a prompt cannot be replaced.
        value = self._client.request(
            "POST",
            self._routes.continue_run(run_id),
            response_model=ApiResearchRunAccepted,
            response_shape=ResponseShape.DIRECT,
            idempotency_key=idempotency_key,
        )
        return value.to_domain()

    def get_run(self, run_id: str) -> ResearchRun:
        value = self._client.get(
            self._routes.run(run_id),
            ApiResearchRun,
            shape=ResponseShape.DIRECT,
        )
        return value.to_domain()

    def list_runs(self, cursor: str | None = None) -> Page[ResearchRun]:
        value = self._client.get(
            self._routes.page(self._routes.RUNS, cursor),
            ApiResearchPage[ApiResearchRun],
            shape=ResponseShape.DIRECT,
        )
        return Page(
            items=[item.to_domain() for item in value.items],
            next_cursor=value.next_cursor,
        )

    def list_threads(self, cursor: str | None = None) -> Page[ResearchThread]:
        value = self._client.get(
            self._routes.page(self._routes.THREADS, cursor),
            ApiResearchPage[ApiResearchThread],
            shape=ResponseShape.DIRECT,
        )
        return Page(
            items=[item.to_domain() for item in value.items],
            next_cursor=value.next_cursor,
        )

    def list_sources(
        self,
        thread_id: str,
        cursor: str | None = None,
    ) -> Page[ResearchSource]:
        value = self._client.get(
            self._routes.sources(thread_id, cursor),
            ApiResearchPage[ApiResearchSource],
            shape=ResponseShape.DIRECT,
        )
        return Page(
            items=[item.to_domain() for item in value.items],
            next_cursor=value.next_cursor,
        )

    def list_artifacts(
        self,
        thread_id: str,
        cursor: str | None = None,
    ) -> Page[ResearchArtifact]:
        value = self._client.get(
            self._routes.artifacts(thread_id, cursor),
            ApiResearchPage[ApiResearchArtifact],
            shape=ResponseShape.DIRECT,
        )
        return Page(
            items=[item.to_domain() for item in value.items],
            next_cursor=value.next_cursor,
        )

    def get_artifact(self, artifact_id: str) -> ResearchArtifact:
        value = self._client.get(
            self._routes.artifact(artifact_id),
            ApiResearchArtifact,
            shape=ResponseShape.DIRECT,
        )
        return value.to_domain()
