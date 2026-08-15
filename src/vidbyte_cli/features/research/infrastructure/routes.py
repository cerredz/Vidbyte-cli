"""FILE: src/vidbyte_cli/features/research/infrastructure/routes.py

PURPOSE: Centralizes every confirmed and assumed public research API path.

ROLE IN CODEBASE: ApiResearchGateway is the only consumer. Opaque path segments are quoted
here so identifiers can never alter route structure.

ARCHITECTURE NOTE: Mutation paths are confirmed from Vidbyte PR #284. Read paths are
explicitly assumed forward contracts until their backend PR lands.

TESTS: No feature tests are added under the approved no-tests workflow. Mock-transport
verification covers path construction before the final draft PR is opened.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode


class ResearchRoutes:
    """Safe constructors for the complete research public surface."""

    CREATE_RUN = "/research/run"
    RUNS = "/research/runs"
    THREADS = "/research/threads"

    def append_run(self, thread_id: str) -> str:
        return f"/research/threads/{self._segment(thread_id)}/run"

    def continue_run(self, run_id: str) -> str:
        return f"/research/runs/{self._segment(run_id)}/continue"

    def run(self, run_id: str) -> str:
        return f"/research/runs/{self._segment(run_id)}"

    def sources(self, thread_id: str, cursor: str | None) -> str:
        path = f"/research/threads/{self._segment(thread_id)}/sources"
        return self._cursor(path, cursor)

    def artifacts(self, thread_id: str, cursor: str | None) -> str:
        path = f"/research/threads/{self._segment(thread_id)}/artifacts"
        return self._cursor(path, cursor)

    def artifact(self, artifact_id: str) -> str:
        return f"/research/artifacts/{self._segment(artifact_id)}"

    def page(self, path: str, cursor: str | None) -> str:
        return self._cursor(path, cursor)

    def _segment(self, value: str) -> str:
        return quote(value, safe="")

    def _cursor(self, path: str, cursor: str | None) -> str:
        if cursor is None:
            return path
        return f"{path}?{urlencode({'cursor': cursor})}"
