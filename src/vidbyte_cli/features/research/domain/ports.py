"""FILE: src/vidbyte_cli/features/research/domain/ports.py

PURPOSE: Defines transport-independent research gateway ports for mutations and persistent
portfolio queries.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import Protocol

from .models import (
    Page,
    ResearchArtifact,
    ResearchRun,
    ResearchRunAccepted,
    ResearchRunRequest,
    ResearchSource,
    ResearchThread,
)


class ResearchGateway(Protocol):
    def start(self, request: ResearchRunRequest, idempotency_key: str) -> ResearchRunAccepted: ...

    def add(
        self,
        thread_id: str,
        request: ResearchRunRequest,
        idempotency_key: str,
    ) -> ResearchRunAccepted: ...

    def resume(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted: ...

    def get_run(self, run_id: str) -> ResearchRun: ...

    def list_runs(self, cursor: str | None = None) -> Page[ResearchRun]: ...

    def list_threads(self, cursor: str | None = None) -> Page[ResearchThread]: ...

    def list_sources(
        self,
        thread_id: str,
        cursor: str | None = None,
    ) -> Page[ResearchSource]: ...

    def list_artifacts(
        self,
        thread_id: str,
        cursor: str | None = None,
    ) -> Page[ResearchArtifact]: ...

    def get_artifact(self, artifact_id: str) -> ResearchArtifact: ...
