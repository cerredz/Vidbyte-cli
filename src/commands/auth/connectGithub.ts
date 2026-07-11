import type { Command } from "commander";
import { notImplemented } from "../../lib/errors/cliError.js";

export class ConnectGithubCommand {
  // Links the user's GitHub account so backend harnesses can clone and open PRs.

  register(parent: Command): void {
    // Attaches `github` under the `vidbyte connect` group.
    parent
      .command("github")
      .description("Connect your GitHub account for harness repository access")
      .action(async () => this.execute());
  }

  private async execute(): Promise<void> {
    // Will start the GitHub App/OAuth install flow and confirm the linkage.
    throw notImplemented("'vidbyte connect github'");
  }
}
