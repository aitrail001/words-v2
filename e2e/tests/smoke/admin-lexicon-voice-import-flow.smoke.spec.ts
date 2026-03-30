import { expect, test } from "@playwright/test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";
const dataRoot = process.env.E2E_WORDS_DATA_ROOT ?? path.join(process.cwd(), "..", "data");

test("@smoke admin can launch voice import from Lexicon Voice and run dry-run/import", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-voice-import-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const runName = `voice-import-smoke-${uniqueSuffix.replace(/[^0-9a-z]/gi, "").toLowerCase()}`;
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

  await rm(hostRunDir, { recursive: true, force: true });
});
