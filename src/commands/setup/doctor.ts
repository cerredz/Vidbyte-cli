import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class DoctorCommand {
  // Diagnoses the local environment: node version, credentials, API connectivity, git.

  register(parent: Command): void {
    // Attaches `vidbyte doctor` to the root program.
    parent
      .command("doctor")
      .description("Check your environment, credentials, and API connectivity")
      .action(async () => this.execute());
  }

  private async execute(): Promise<void> {
    // Will run each diagnostic check and print a pass/fail report.
    throw notImplemented("'vidbyte doctor'");
  }
}
