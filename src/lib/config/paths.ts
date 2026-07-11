import { homedir } from "node:os";
import { join } from "node:path";

export class VidbytePaths {
  // Single source of truth for every file path the CLI reads or writes under ~/.vidbyte.

  static root(): string {
    // Returns the ~/.vidbyte directory that holds all CLI state.
    return join(homedir(), ".vidbyte");
  }

  static credentialsFile(): string {
    // Returns the path of the JSON file storing the user's Vidbyte API key.
    return join(VidbytePaths.root(), "credentials.json");
  }

  static configFile(): string {
    // Returns the path of the JSON file storing non-secret CLI configuration.
    return join(VidbytePaths.root(), "config.json");
  }
}
