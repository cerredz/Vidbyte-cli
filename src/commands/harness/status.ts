import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class HarnessStatusCommand {
  // Shows the status, event log, and result of one harness run.

  register(parent: Command): void {
    // Attaches `status <runId>` under the `vidbyte harness` group.
    parent
      .command("status <runId>")
      .description("Show the status and events of a harness run")
      .action(async (runId: string) => this.execute(runId));
  }

  private async execute(runId: string): Promise<void> {
    // Will fetch the run from the backend and render its status block.
    throw notImplemented("'vidbyte harness status'");
  }
}
