"""FILE: src/vidbyte_cli/features/research/infrastructure/api_gateway.py

PURPOSE: Implements ResearchGateway over the Vidbyte public API with confirmed mutation
routes, assumed forward read/export routes, strict direct DTO decoding, and capability
validation.

ROLE IN CODEBASE: ApplicationContext lazily creates this adapter only when a research
command executes. Domain/application/command layers never import it.

ARCHITECTURE NOTE: Every POST receives the caller's one stable idempotency key. Continue
sends no prompt and no body. Route assumptions are isolated in routes.py, and provider-key
fields have no representation in the request DTO.

TESTS: No feature tests are added under the approved no-tests workflow. An HTTPX
MockTransport verification exercises exact methods, paths, bodies, headers, and mappings.
"""

from __future__ import annotations

from typing import NoReturn

from ....lib.api.client import ApiClient
from ....lib.api.response import ResponseShape
from ....lib.errors import CliError, CliErrorCode, usage_error
from ..domain import (
    Page,
    ResearchArtifact,
    ResearchCapabilities,
    ResearchExport,
    ResearchExportRequest,
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
    ApiResearchCapabilities,
    ApiResearchExport,
    ApiResearchExportRequest,
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
        self._capabilities: ResearchCapabilities | None = None

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
        self._require_read_contract()
        value = self._client.get(
            self._routes.run(run_id),
            ApiResearchRun,
            shape=ResponseShape.DIRECT,
        )
        return value.to_domain()

    def list_runs(self, cursor: str | None = None) -> Page[ResearchRun]:
        self._require_read_contract()
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
        self._require_read_contract()
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
        self._require_read_contract()
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
        self._require_read_contract()
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
        self._require_read_contract()
        value = self._client.get(
            self._routes.artifact(artifact_id),
            ApiResearchArtifact,
            shape=ResponseShape.DIRECT,
        )
        return value.to_domain()

    def capabilities(self) -> ResearchCapabilities:
        if self._capabilities is not None:
            return self._capabilities
        try:
            value = self._client.get(
                self._routes.CAPABILITIES,
                ApiResearchCapabilities,
                shape=ResponseShape.DIRECT,
            )
        except CliError as error:
            self._raise_capability_version_error(error)
        self._capabilities = value.to_domain()
        return self._capabilities

    def export(
        self,
        request: ResearchExportRequest,
        idempotency_key: str,
    ) -> ResearchExport:
        capabilities = self.capabilities()
        if request.provider not in capabilities.export_providers:
            raise usage_error(
                f"Export provider '{request.provider}' is not available.",
                "Run 'vidbyte-cli research capabilities' to list available providers.",
            )
        try:
            value = self._client.post(
                self._routes.EXPORTS,
                ApiResearchExportRequest.from_domain(request),
                ApiResearchExport,
                idempotency_key=idempotency_key,
                shape=ResponseShape.DIRECT,
            )
        except CliError as error:
            self._raise_export_version_error(error)
        return value.to_domain()

    def get_export(self, export_id: str) -> ResearchExport:
        self._require_read_contract()
        try:
            value = self._client.get(
                self._routes.export(export_id),
                ApiResearchExport,
                shape=ResponseShape.DIRECT,
            )
        except CliError as error:
            self._raise_export_version_error(error)
        return value.to_domain()

    def _require_read_contract(self) -> None:
        # Capabilities are cached per invocation and double as the forward API-version probe.
        self.capabilities()

    def _raise_capability_version_error(self, error: CliError) -> NoReturn:
        if error.code is not CliErrorCode.OPERATION_FAILED:
            raise error
        raise CliError(
            CliErrorCode.API_PROTOCOL_ERROR,
            "This Vidbyte API does not expose the research capability contract.",
            hint="Upgrade the API deployment or use a compatible CLI version.",
            cause=error,
        ) from error

    def _raise_export_version_error(self, error: CliError) -> NoReturn:
        if error.code is not CliErrorCode.OPERATION_FAILED:
            raise error
        raise CliError(
            CliErrorCode.API_PROTOCOL_ERROR,
            "This Vidbyte API does not expose the research export contract.",
            hint="Upgrade the API deployment or use a compatible CLI version.",
            cause=error,
        ) from error
