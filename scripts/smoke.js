// Build sanity check: the compiled CLI must boot and print its own help text.
import { spawnSync } from "node:child_process";

const result = spawnSync(process.execPath, ["bin/vidbyte.js", "--help"], { encoding: "utf8" });

if (result.status !== 0 || !result.stdout.includes("vidbyte")) {
  console.error("smoke test failed: `vidbyte --help` did not exit 0 with help output");
  console.error(result.stdout || "");
  console.error(result.stderr || "");
  process.exit(1);
}

console.log("smoke ok: `vidbyte --help` works");
