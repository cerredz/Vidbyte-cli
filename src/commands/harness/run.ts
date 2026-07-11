import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class HarnessRunCommand {
  // Submits a new harness run for the current repository to the Vidbyte backend.

  register(parent: Command): void {
    // Attaches `run <name>` with its options under the `vidbyte harness` group.
    parent
      .command("run <name>")
      .description("Run a Vidbyte harness against the current repository")
      .requiredOption("--task <task>", "what the harness should do")
      .action(async (name: string, options: { task: string }) => this.execute(name, options));
  }

  private async execute(name: string, options: { task: string }): Promise<void> {
    // Will inspect the local repo, submit the run, and stream status until done.
    throw notImplemented("'vidbyte harness run'");
  }
}
