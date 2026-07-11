import { Command } from "commander";
import { registerAllCommands } from "./commands/index.js";
import { CliError } from "./lib/errors/cliError.js";
import { logger } from "./lib/output/logger.js";

const CLI_VERSION = "0.1.0";

export async function main(argv: string[]): Promise<void> {
  // Builds the root commander program, registers all command groups, and dispatches argv.
  const program = new Command();
  program
    .name("vidbyte")
    .description("Universal Vidbyte CLI: authentication, harness runs, and configuration")
    .version(CLI_VERSION)
    .option("--json", "machine-readable output (reserved)");
  registerAllCommands(program);
  await program.parseAsync(argv);
}

main(process.argv).catch((error: unknown) => {
  // Central error trap: CliErrors exit with their own code; anything else is a bug (exit 70).
  if (error instanceof CliError) {
    logger.error(error.message);
    process.exit(error.exitCode);
  }
  logger.error(String(error));
  process.exit(70);
});
