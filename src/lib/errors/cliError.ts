export class CliError extends Error {
  // User-facing CLI failure carrying the exact process exit code to terminate with.
  readonly exitCode: number;

  constructor(message: string, exitCode = 1) {
    // Builds a CLI-facing error; the central trap in index.ts renders it and exits.
    super(message);
    this.name = "CliError";
    this.exitCode = exitCode;
  }
}

export function notImplemented(subject: string): CliError {
  // Standard stub error for scaffolded behavior that is not built yet.
  return new CliError(`${subject} is not implemented yet.`, 1);
}
