import type { ApiClient } from "../client.js";
import type { WhoAmI } from "../../../types/api.js";

export class AuthEndpoints {
  // Typed wrappers for authentication-related backend routes.

  constructor(private readonly client: ApiClient) {
    // Binds the endpoint group to a configured ApiClient.
  }

  async whoami(): Promise<WhoAmI> {
    // Resolves the identity behind the configured API key.
    return this.client.get<WhoAmI>("/auth/whoami");
  }
}
