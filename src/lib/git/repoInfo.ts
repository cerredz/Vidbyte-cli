import { notImplemented } from "../errors/cliError.js";

export interface RepoInfo {
  originUrl: string;
  headSha: string;
  branch: string;
  isDirty: boolean;
}

export class RepoInspector {
  // Reads identifying facts about the git repository in the current working directory,
  // so `harness run` can tell the backend exactly which code to run against.

  async inspect(): Promise<RepoInfo> {
    // Returns origin URL, HEAD sha, current branch, and dirty state for cwd's repo.
    throw notImplemented("repository inspection");
  }
}
