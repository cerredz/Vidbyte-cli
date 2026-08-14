"""Typed wrappers for the /api/v1/research/* public API routes.

These six are the entire surface an API key may call. There is no sources, artifacts,
capabilities, exports, or run-listing route, so there is no method here for one.

Every route returns its DTO directly rather than inside the `{success, data}` envelope the
older public resources use, which is why each call names `ResponseShape.DIRECT` explicitly.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from ....types.research import (
    ResearchPortfolioPage,
    ResearchRunAccepted,
    ResearchRunCreateRequest,
    ResearchRunStatus,
    ResearchThreadDetail,
)
from ..client import ApiClient
from ..response import ResponseShape

_RESEARCH_ROOT = "/api/v1/research"


class ResearchEndpoints:
    def __init__(self, client: ApiClient) -> None:
        # Binds the endpoint group to a configured ApiClient.
        self._client = client

    def create_run(
        self,
        request: ResearchRunCreateRequest,
        idempotency_key: str,
    ) -> ResearchRunAccepted:
        # POST /api/v1/research/run — opens a new thread and admits its first run.
        return self._client.post(
            f"{_RESEARCH_ROOT}/run",
            request,
            ResearchRunAccepted,
            shape=ResponseShape.DIRECT,
            idempotency_key=idempotency_key,
        )

    def append_run(
        self,
        thread_id: str,
        request: ResearchRunCreateRequest,
        idempotency_key: str,
    ) -> ResearchRunAccepted:
        # POST /api/v1/research/threads/{id}/run — admits another prompt into one thread.
        return self._client.post(
            f"{_RESEARCH_ROOT}/threads/{self._segment(thread_id)}/run",
            request,
            ResearchRunAccepted,
            shape=ResponseShape.DIRECT,
            idempotency_key=idempotency_key,
        )

    def continue_run(self, run_id: str, idempotency_key: str) -> ResearchRunAccepted:
        # POST /api/v1/research/runs/{id}/continue — reopens one terminal-resumable run.
        # The route takes no body: a continuation replays the original prompt, never a new one.
        return self._client.request(
            "POST",
            f"{_RESEARCH_ROOT}/runs/{self._segment(run_id)}/continue",
            response_model=ResearchRunAccepted,
            response_shape=ResponseShape.DIRECT,
            idempotency_key=idempotency_key,
        )

    def get_run(self, run_id: str) -> ResearchRunStatus:
        # GET /api/v1/research/runs/{id} — one run's coarse durable status.
        return self._client.get(
            f"{_RESEARCH_ROOT}/runs/{self._segment(run_id)}",
            ResearchRunStatus,
            shape=ResponseShape.DIRECT,
        )

    def get_portfolio(self, cursor: str | None, limit: int | None) -> ResearchPortfolioPage:
        # GET /api/v1/research/portfolio — one bounded page of the caller's threads.
        return self._client.get(
            self._paged(f"{_RESEARCH_ROOT}/portfolio", cursor, limit),
            ResearchPortfolioPage,
            shape=ResponseShape.DIRECT,
        )

    def get_thread(self, thread_id: str) -> ResearchThreadDetail:
        # GET /api/v1/research/threads/{id} — one owned thread and its rollup counters.
        return self._client.get(
            f"{_RESEARCH_ROOT}/threads/{self._segment(thread_id)}",
            ResearchThreadDetail,
            shape=ResponseShape.DIRECT,
        )

    def _segment(self, value: str) -> str:
        # Encoding an opaque identifier means it can never alter the route's structure.
        return quote(value, safe="")

    def _paged(self, path: str, cursor: str | None, limit: int | None) -> str:
        # Unset parameters are omitted so the server keeps ownership of both defaults.
        query = {name: value for name, value in (("cursor", cursor), ("limit", limit)) if value}
        return f"{path}?{urlencode(query)}" if query else path
