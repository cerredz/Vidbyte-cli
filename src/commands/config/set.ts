import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class ConfigSetCommand {
  // Sets one CLI configuration key to a new value.

  register(parent: Command): void {
    // Attaches `set <key> <value>` under the `vidbyte config` group.
    parent
      .command("set <key> <value>")
      .description("Set a CLI configuration value")
      .action(async (key: string, value: string) => this.execute(key, value));
  }

  private async execute(key: string, value: string): Promise<void> {
    // Will validate the key and persist the value in the config store.
    throw notImplemented("'vidbyte config set'");
  }
}
