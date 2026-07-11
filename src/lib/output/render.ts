import { notImplemented } from "../errors/cliError.js";
import type { HarnessRun } from "../../types/api.js";

export class RunRenderer {
  // Renders harness runs for human-readable terminal output.

  renderStatus(run: HarnessRun): string {
    // Formats one run's status, latest events, and result into a terminal block.
    throw notImplemented("run status rendering");
  }

  renderList(runs: HarnessRun[]): string {
    // Formats a list of runs into an aligned summary table.
    throw notImplemented("run list rendering");
  }
}
