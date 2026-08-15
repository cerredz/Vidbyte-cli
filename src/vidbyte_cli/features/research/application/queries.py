"""FILE: src/vidbyte_cli/features/research/application/queries.py

PURPOSE: Provides thin typed query use cases over ResearchGateway with cursor and
opaque-identifier validation independent of Click and HTTP.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from ....lib.errors.cli_error import CliError
from ....lib.errors.codes import CliErrorCode
from ..domain import (
    Page,
    ResearchArtifact,
    ResearchGateway,
    ResearchRun,
    ResearchSource,
    ResearchThread,
)


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

    def _require_id(self, value: str) -> None:
        if not 1 <= len(value) <= 200:
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                "A research resource identifier is empty or too large.",
                2,
            )
