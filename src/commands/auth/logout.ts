import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class LogoutCommand {
  // Removes stored credentials from the local machine.

  register(parent: Command): void {
    // Attaches `vidbyte logout` to the root program.
    parent
      .command("logout")
      .description("Remove stored Vidbyte credentials from this machine")
      .action(async () => this.execute());
  }

  private async execute(): Promise<void> {
    // Will clear the credential store and confirm to the user.
    throw notImplemented("'vidbyte logout'");
  }
}
