import path from "node:path";

function resolveWorkspaceDataRoot(): string {
  const cwd = process.cwd();
  if (path.basename(cwd) === "e2e") {
    return path.resolve(cwd, "..", "data");
  }
  return path.resolve(cwd, "data");
}

export const hostWordsDataRoot =
  process.env.E2E_WORDS_DATA_ROOT ??
  process.env.WORDS_DATA_DIR ??
  resolveWorkspaceDataRoot();

export const backendWordsDataRoot =
  process.env.E2E_BACKEND_WORDS_DATA_ROOT ??
  (process.env.CI ? "/app/data" : hostWordsDataRoot);
