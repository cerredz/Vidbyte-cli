export class Logger {
  // Leveled console logger; the seam where --json / quiet modes will hook in later.

  info(message: string): void {
    // Prints an informational line to stdout.
    console.log(message);
  }

  warn(message: string): void {
    // Prints a warning line to stderr.
    console.error(message);
  }

  error(message: string): void {
    // Prints an error line to stderr.
    console.error(message);
  }
}

export const logger = new Logger();
