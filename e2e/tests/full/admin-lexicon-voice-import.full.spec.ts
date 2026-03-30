import { expect, test } from "@playwright/test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { apiUrl, authHeaders, injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";
const dataRoot = process.env.E2E_WORDS_DATA_ROOT ?? path.join(process.cwd(), "..", "data");

test("admin can launch voice import from Lexicon Voice and complete a persisted import", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-voice-import-full");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const runName = `voice-import-full-${uniqueSuffix.replace(/[^0-9a-z]/gi, "").toLowerCase()}`;
  const hostRunDir = path.join(dataRoot, "lexicon", "voice", runName);
  const manifestHostPath = path.join(hostRunDir, "voice_manifest.jsonl");

  await rm(hostRunDir, { recursive: true, force: true });
  await mkdir(hostRunDir, { recursive: true });
  await writeFile(
    manifestHostPath,
    `${JSON.stringify({
      status: "generated",
      entry_type: "word",
      entry_id: `word:${runName}`,
      word: runName,
      language: "en",
      source_reference: runName,
      content_scope: "word",
      source_text: runName,
      locale: "en-US",
      voice_role: "female",
      provider: "google",
      family: "neural2",
      voice_id: "en-US-Neural2-C",
      profile_key: "word",
      audio_format: "mp3",
      mime_type: "audio/mpeg",
      storage_kind: "local",
      storage_base: hostRunDir,
      relative_path: `${runName}.mp3`,
      source_text_hash: `hash-${runName}`,
    })}\n`,
    "utf-8",
  );

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);

  await page.goto(`${adminUrl}/lexicon/voice`);
  await expect(page.getByTestId("lexicon-voice-page")).toBeVisible();
  await expect(page.getByTestId("lexicon-voice-runs")).toContainText(runName);
  await page.getByTestId(`lexicon-voice-run-import-${runName}`).click();

  await expect(page).toHaveURL(/\/lexicon\/voice-import/);
  await expect(page.getByTestId("lexicon-voice-import-input-path")).toHaveValue(new RegExp(`${runName}/voice_manifest\\.jsonl$`));

  await page.getByTestId("lexicon-voice-import-dry-run").click();
  await expect(page.getByText("Voice import dry-run complete.")).toBeVisible();
  await expect(page.getByTestId("lexicon-voice-import-result")).toContainText("Rows");
  await expect(page.getByTestId("lexicon-voice-import-result")).toContainText("Generated");

  await page.getByTestId("lexicon-voice-import-run").click();
  await expect(page.getByTestId("lexicon-voice-import-progress")).toBeVisible();
  await expect(page.getByTestId("lexicon-voice-import-progress")).not.toContainText("Waiting for first row...");
  await expect(page.getByTestId("lexicon-voice-import-progress")).toContainText(/Current entry: (Validating|Importing|Completed)/);
  await expect(page.getByTestId("lexicon-voice-import-recent-jobs")).toContainText(runName);

  const deadline = Date.now() + 30_000;
  let terminalJob:
    | {
        status: "queued" | "running" | "completed" | "failed";
        target_key: string;
        request_payload: { input_path?: string };
        error_message: string | null;
      }
    | null = null;
  while (Date.now() <= deadline) {
    const response = await request.get(`${apiUrl}/lexicon-jobs?job_type=voice_import_db&limit=24`, {
      headers: authHeaders(user.token),
    });
    expect(response.ok()).toBeTruthy();
    const jobs = (await response.json()) as Array<{
      status: "queued" | "running" | "completed" | "failed";
      target_key: string;
      request_payload: { input_path?: string };
      error_message: string | null;
    }>;
    const matchedJob =
      jobs.find((job) => {
        const inputPath = typeof job.request_payload?.input_path === "string" ? job.request_payload.input_path : "";
        return job.target_key.includes(runName) || inputPath.includes(runName);
      }) ?? null;
    if (matchedJob && (matchedJob.status === "completed" || matchedJob.status === "failed")) {
      terminalJob = matchedJob;
      break;
    }
    await page.waitForTimeout(1_000);
  }

  expect(terminalJob).not.toBeNull();
  expect(terminalJob?.status).toBe("completed");
  expect(terminalJob?.error_message).toBeNull();
  await expect(page.getByText("Voice import completed.")).toBeVisible();
  await expect(page.getByTestId("lexicon-voice-import-progress")).toContainText("Completed");

  await rm(hostRunDir, { recursive: true, force: true });
});
