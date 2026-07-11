import type { Command } from "commander";
import { LoginCommand } from "./auth/login.js";
import { LogoutCommand } from "./auth/logout.js";
import { WhoamiCommand } from "./auth/whoami.js";
import { ConnectGithubCommand } from "./auth/connectGithub.js";
import { HarnessRunCommand } from "./harness/run.js";
import { HarnessStatusCommand } from "./harness/status.js";
import { HarnessListCommand } from "./harness/list.js";
import { ConfigGetCommand } from "./config/get.js";
import { ConfigSetCommand } from "./config/set.js";
import { DoctorCommand } from "./setup/doctor.js";

export function registerAllCommands(program: Command): void {
  // Single registration point: attaches every command group to the root program.
  new LoginCommand().register(program);
  new LogoutCommand().register(program);
  new WhoamiCommand().register(program);
  new DoctorCommand().register(program);

  const connect = program.command("connect").description("Connect external accounts to Vidbyte");
  new ConnectGithubCommand().register(connect);

  const harness = program.command("harness").description("Run and inspect Vidbyte harnesses");
  new HarnessRunCommand().register(harness);
  new HarnessStatusCommand().register(harness);
  new HarnessListCommand().register(harness);

  const config = program.command("config").description("Manage CLI configuration");
  new ConfigGetCommand().register(config);
  new ConfigSetCommand().register(config);
}
