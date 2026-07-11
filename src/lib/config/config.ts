import { notImplemented } from "../errors/cliError.js";

export class ConfigStore {
  // Reads and writes non-secret CLI settings at ~/.vidbyte/config.json.

  async get(key: string): Promise<string | undefined> {
    // Returns the stored value for a config key, or undefined when unset.
    throw notImplemented("config store reads");
  }

  async set(key: string, value: string): Promise<void> {
    // Persists a config key/value pair, creating ~/.vidbyte on first write.
    throw notImplemented("config store writes");
  }
}
