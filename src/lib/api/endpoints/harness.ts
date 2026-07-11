import type { ApiClient } from "../client.js";
import type { HarnessRun, HarnessRunCreateRequest } from "../../../types/api.js";

export class HarnessEndpoints {
  // Typed wrappers for the backend /harness/* public API routes.

  constructor(private readonly client: ApiClient) {
    // Binds the endpoint group to a configured ApiClient.
  }

  async createRun(request: HarnessRunCreateRequest): Promise<HarnessRun> {
    // POST /harness/run — submits a new run and returns it in `queued` state.
    return this.client.post<HarnessRun>("/harness/run", request);
  }

  async getRun(runId: string): Promise<HarnessRun> {
    // GET /harness/get/{run_id} — returns the run's status, events, and result.
    return this.client.get<HarnessRun>(`/harness/get/${encodeURIComponent(runId)}`);
  }

  async listRuns(): Promise<HarnessRun[]> {
    // GET /harness/list — returns the caller's runs, newest first.
    return this.client.get<HarnessRun[]>("/harness/list");
  }
}
