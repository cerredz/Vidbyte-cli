import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class HarnessListCommand {
  // Lists the caller's harness runs, newest first.

  register(parent: Command): void {
    // Attaches `list` under the `vidbyte harness` group.
    parent
      .command("list")
      .description("List your harness runs")
      .action(async () => this.execute());
  }

  private async execute(): Promise<void> {
    // Will fetch the caller's runs and render them as a summary table.
    throw notImplemented("'vidbyte harness list'");
  }
}
