import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class ConfigGetCommand {
  // Prints the value of one CLI configuration key.

  register(parent: Command): void {
    // Attaches `get <key>` under the `vidbyte config` group.
    parent
      .command("get <key>")
      .description("Print a CLI configuration value")
      .action(async (key: string) => this.execute(key));
  }

  private async execute(key: string): Promise<void> {
    // Will read the key from the config store and print it.
    throw notImplemented("'vidbyte config get'");
  }
}
