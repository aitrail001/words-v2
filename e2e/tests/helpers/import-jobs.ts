import { APIRequestContext, expect } from "@playwright/test";
import { apiUrl } from "./auth";

export type ImportJobSnapshot = {
  id: string;
  status: "queued" | "processing" | "completed" | "failed";
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  book_id: string | null;
  word_list_id: string | null;
  total_items: number;
  processed_items: number;
  error_count: number;
};

const TERMINAL_STATUSES = new Set<ImportJobSnapshot["status"]>(["completed", "failed"]);

export const waitForImportJobTerminal = async (
  request: APIRequestContext,
  token: string,
  jobId: string,
  options: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<ImportJobSnapshot> => {
  const timeoutMs = options.timeoutMs ?? 120_000;
  const pollIntervalMs = options.pollIntervalMs ?? 1_500;
  const deadline = Date.now() + timeoutMs;

  let latest: ImportJobSnapshot | null = null;
  while (Date.now() <= deadline) {
    const response = await request.get(`${apiUrl}/import-jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    latest = (await response.json()) as ImportJobSnapshot;

    if (TERMINAL_STATUSES.has(latest.status)) {
      return latest;
    }

    await new Promise((resolve) => {
      setTimeout(resolve, pollIntervalMs);
    });
  }

  throw new Error(
    `Timed out waiting for terminal import status for ${jobId}; last=${latest?.status ?? "unknown"}`,
  );
};
