"""FILE: src/vidbyte_cli/features/research/application/queries.py

PURPOSE: Provides thin typed query/export use cases over ResearchGateway with cursor and
opaque-identifier validation independent of Click and HTTP.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib

from ....lib.errors.cli_error import CliError
from ....lib.errors.codes import CliErrorCode
from ..domain import (
    Page,
    ResearchArtifact,
    ResearchCapabilities,
    ResearchExport,
    ResearchExportRequest,
    ResearchGateway,
    ResearchRun,
    ResearchSource,
    ResearchThread,
)
from .ports import IdempotencyProvider, OperationRecorder


class ResearchQueryService:
    def __init__(self, gateway: ResearchGateway) -> None:
        self._gateway = gateway

    def status(self, run_id: str) -> ResearchRun:
        self._require_id(run_id)
        return self._gateway.get_run(run_id)

    def runs(self, cursor: str | None = None) -> Page[ResearchRun]:
        return self._gateway.list_runs(cursor)

    def threads(self, cursor: str | None = None) -> Page[ResearchThread]:
        return self._gateway.list_threads(cursor)

    def sources(self, thread_id: str, cursor: str | None = None) -> Page[ResearchSource]:
        self._require_id(thread_id)
        return self._gateway.list_sources(thread_id, cursor)

    def artifacts(self, thread_id: str, cursor: str | None = None) -> Page[ResearchArtifact]:
        self._require_id(thread_id)
        return self._gateway.list_artifacts(thread_id, cursor)

    def artifact(self, artifact_id: str) -> ResearchArtifact:
        self._require_id(artifact_id)
        return self._gateway.get_artifact(artifact_id)

    def capabilities(self) -> ResearchCapabilities:
        return self._gateway.capabilities()

    def _require_id(self, value: str) -> None:
        if not 1 <= len(value) <= 200:
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                "A research resource identifier is empty or too large.",
                2,
            )


class ResearchExportService:
    def __init__(
        self,
        gateway: ResearchGateway,
        idempotency: IdempotencyProvider,
        journal: OperationRecorder,
    ) -> None:
        self._gateway = gateway
        self._idempotency = idempotency
        self._journal = journal

    def create(
        self,
        request: ResearchExportRequest,
        explicit_key: str | None = None,
    ) -> ResearchExport:
        key = self._idempotency.create(explicit_key)
        fingerprint = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()
        self._journal.begin(
            key,
            f"research export {request.scope.value}",
            key,
            fingerprint,
            f"Retry export with idempotency key {key}",
        )
        export = self._gateway.export(request, key)
        self._journal.accepted(
            key,
            export.export_id,
            f"vidbyte-cli research export status {export.export_id}",
        )
        return export

    def get(self, export_id: str) -> ResearchExport:
        if not 1 <= len(export_id) <= 200:
            raise CliError(CliErrorCode.INVALID_ARGUMENT, "Invalid export identifier.", 2)
        return self._gateway.get_export(export_id)
