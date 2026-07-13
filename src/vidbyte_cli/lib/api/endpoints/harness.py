"""Typed wrappers for the backend /harness/* public API routes."""

from __future__ import annotations

from ....types.api import HarnessRun, HarnessRunCreateRequest, HarnessSummary
from ....types.manifest import HarnessManifest
from ..client import ApiClient


class HarnessEndpoints:
    def __init__(self, client: ApiClient) -> None:
        # Binds the endpoint group to a configured ApiClient.
        self._client = client

    def create_run(self, request: HarnessRunCreateRequest) -> HarnessRun:
        # POST /harness/run — submits a new run and returns it in `queued` state.
        return self._client.post("/harness/run", request, HarnessRun)

    def get_run(self, run_id: str) -> HarnessRun:
        # GET /harness/get/{run_id} — returns the run's status, events, and result.
        return self._client.get(f"/harness/get/{run_id}", HarnessRun)

    def list_runs(self) -> list[HarnessRun]:
        # GET /harness/list — returns the caller's runs, newest first.
        return self._client.get_list("/harness/list", HarnessRun)

    def get_manifest(self, name: str) -> HarnessManifest:
        # GET /harness/{name}/manifest — the command surface the dynamic runtime renders
        # into click commands (resolves the endpoints/harness.ts:4 review comment). Chosen
        # over one big /harness/manifest so a namespace loads lazily, one round-trip each.
        return self._client.get(f"/harness/{name}/manifest", HarnessManifest)

    def list_catalog(self) -> list[HarnessSummary]:
        # GET /harness/catalog — the available harnesses, distinct from the caller's runs.
        return self._client.get_list("/harness/catalog", HarnessSummary)
