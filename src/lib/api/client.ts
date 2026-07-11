import { notImplemented } from "../errors/cliError.js";

export const DEFAULT_API_URL = "https://api.vidbyte.ai";

export interface ApiClientOptions {
  baseUrl?: string;
  apiKey?: string;
}

export class ApiClient {
  // Typed HTTP client for the Vidbyte public API: owns the base URL, API-key header
  // injection, and response-envelope unwrapping. Commands never call fetch directly.
  private readonly baseUrl: string;
  private readonly apiKey: string | undefined;

  constructor(options: ApiClientOptions = {}) {
    // Resolves the API host from options, then VIDBYTE_API_URL, then the production default.
    this.baseUrl = options.baseUrl ?? process.env.VIDBYTE_API_URL ?? DEFAULT_API_URL;
    this.apiKey = options.apiKey ?? process.env.VIDBYTE_API_KEY;
  }

  async get<T>(path: string): Promise<T> {
    // Performs an authenticated GET and unwraps the standard response envelope.
    throw notImplemented("api client requests");
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    // Performs an authenticated POST and unwraps the standard response envelope.
    throw notImplemented("api client requests");
  }
}
