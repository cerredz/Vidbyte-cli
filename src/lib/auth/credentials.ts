import { notImplemented } from "../errors/cliError.js";

export interface Credentials {
  apiKey: string;
}

export class CredentialStore {
  // Reads and writes the user's Vidbyte API key at ~/.vidbyte/credentials.json.
  // The key is a secret: it must never be logged or included in error messages.

  async read(): Promise<Credentials | null> {
    // Returns stored credentials, or null when the user has never logged in.
    throw notImplemented("credential store reads");
  }

  async write(credentials: Credentials): Promise<void> {
    // Persists credentials with owner-only file permissions where supported.
    throw notImplemented("credential store writes");
  }

  async clear(): Promise<void> {
    // Deletes stored credentials; safe to call when none exist.
    throw notImplemented("credential store clearing");
  }
}
