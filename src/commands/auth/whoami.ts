import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class WhoamiCommand {
  // Shows which Vidbyte account the stored credentials belong to.

  register(parent: Command): void {
    // Attaches `vidbyte whoami` to the root program.
    parent
      .command("whoami")
      .description("Show the Vidbyte account behind the stored credentials")
      .action(async () => this.execute());
  }

  private async execute(): Promise<void> {
    // Will call the auth endpoint with stored credentials and print the identity.
    throw notImplemented("'vidbyte whoami'");
  }
}
