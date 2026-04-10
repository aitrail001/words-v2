import { expect, test } from "@playwright/test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { authHeaders, injectAdminToken, registerAdminViaApi, waitForAppReady, apiUrl } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";
const dataRoot = process.env.E2E_WORDS_DATA_ROOT ?? process.env.WORDS_DATA_DIR ?? path.join(process.cwd(), "data");

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

  await expect
    .poll(
      async () => {
        const response = await request.get(`${apiUrl}/lexicon-ops/voice-runs?q=${encodeURIComponent(runName)}`, {
          headers: authHeaders(user.token),
          timeout: 30_000,
        });
        if (!response.ok()) {
          return false;
        }
        const runs = (await response.json()) as { items: Array<{ run_name: string }> };
        return runs.items.some((run) => run.run_name === runName);
      },
      {
        timeout: 15_000,
        intervals: [250, 500, 1_000],
      },
    )
    .toBeTruthy();

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);

  await page.goto(`${adminUrl}/lexicon/voice-runs`);
  await expect(page.getByTestId("lexicon-voice-page")).toBeVisible();
  await page.getByTestId("lexicon-voice-runs-search").fill(runName);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId(`lexicon-voice-run-import-${runName}`)).toBeVisible({ timeout: 30_000 });
  await page.getByTestId(`lexicon-voice-run-import-${runName}`).click();

  await expect(page).toHaveURL(/\/lexicon\/voice-import/);
  await expect(page.getByTestId("lexicon-voice-import-input-path")).toHaveValue(new RegExp(`${runName}/voice_manifest\\.jsonl$`));

  await page.getByTestId("lexicon-voice-import-dry-run").click();
  await expect(page.getByText("Voice import dry-run complete.")).toBeVisible();
  await expect(page.getByTestId("lexicon-voice-import-result")).toContainText("Rows");
  await expect(page.getByTestId("lexicon-voice-import-result")).toContainText("Generated");

  await page.getByTestId("lexicon-voice-import-run").click();
  await expect(page.getByTestId("lexicon-voice-import-progress")).toBeVisible();
  await expect(page.getByTestId("lexicon-voice-import-progress")).toContainText(/Current entry:/);
  await expect(page.getByTestId("lexicon-voice-import-progress")).toContainText(/(queued|running|completed|validating|importing)/i);
  await expect(page.getByTestId("lexicon-voice-import-recent-jobs")).toContainText(runName);

  await rm(hostRunDir, { recursive: true, force: true });
});
