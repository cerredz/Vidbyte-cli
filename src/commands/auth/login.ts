import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class LoginCommand {
  // Stores the user's Vidbyte API key so every later command can authenticate.

  register(parent: Command): void {
    // Attaches `vidbyte login` to the root program.
    parent
      .command("login")
      .description("Authenticate the CLI with your Vidbyte API key")
      .action(async () => this.execute());
  }

  private async execute(): Promise<void> {
    // Will prompt for the API key, verify it against the backend, and persist it.
    throw notImplemented("'vidbyte login'");
  }
}
