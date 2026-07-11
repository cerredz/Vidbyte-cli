// Response envelope and resource types mirroring the Vidbyte backend public API DTOs.
// Keep field names in sync with backend/lib/dtos/harness.py once those routes ship.

export interface ApiEnvelope<T> {
  success: boolean;
  message?: string;
  data?: T;
  error?: ApiError;
  pagination?: ApiPagination;
}

export interface ApiError {
  code: string;
  title: string;
  detail: string;
}

export interface ApiPagination {
  limit: number;
  page: number;
  total?: number;
}

export interface HarnessRepoRef {
  url: string;
  sha: string;
  branch?: string | null;
}

export interface HarnessRunCreateRequest {
  harness: string;
  task: string;
  repo: HarnessRepoRef;
}

export interface HarnessRunEvent {
  type: "status" | "log" | "error";
  message: string;
  created_at: string;
}

export interface HarnessRunResult {
  branch?: string | null;
  pr_url?: string | null;
  summary?: string | null;
}

export interface HarnessRun {
  run_id: string;
  harness: string;
  status: "queued" | "running" | "completed" | "failed";
  task: string;
  repo: HarnessRepoRef;
  events: HarnessRunEvent[];
  result?: HarnessRunResult | null;
  created_at: string;
  updated_at: string;
}

export interface WhoAmI {
  user_id: string;
  email?: string;
}
