import { expect, test } from "@playwright/test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { apiUrl, authHeaders, injectAdminToken, registerAdminViaApi } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

const buildCompiledWordRow = (runId: string, word: string) => ({
  schema_version: "1.1.0",
  entry_id: `word:${word}:${runId}`,
  entry_type: "word",
  normalized_form: word,
  source_provenance: [{ source: "e2e-smoke", run_id: runId }],
  entity_category: "general",
  word,
  part_of_speech: ["noun"],
  cefr_level: "B1",
  frequency_rank: 100,
  phonetics: {
    us: { ipa: `/${word}/`, confidence: 0.99 },
    uk: { ipa: `/${word}/`, confidence: 0.98 },
    au: { ipa: `/${word}/`, confidence: 0.97 },
  },
  forms: {
    plural_forms: [`${word}s`],
    verb_forms: {},
    comparative: null,
    superlative: null,
    derivations: [],
  },
  senses: [
    {
      sense_id: `sense-${runId}-1`,
      definition: `a learner-facing definition for ${word}`,
      examples: [{ sentence: `The ${word} is visible.`, difficulty: "easy" }],
      translations: {
        "zh-Hans": { definition: `${word} 的定义`, usage_note: "常见义项", examples: [`这个${word}很明显。`] },
        es: { definition: `definicion de ${word}`, usage_note: "uso comun", examples: [`El ${word} es visible.`] },
        ar: { definition: `تعريف ${word}`, usage_note: "معنى شائع", examples: [`هذا ${word} واضح.`] },
        "pt-BR": { definition: `definicao de ${word}`, usage_note: "uso comum", examples: [`O ${word} esta visivel.`] },
        ja: { definition: `${word} の定義`, usage_note: "よくある意味", examples: [`その${word}が見える。`] },
      },
    },
  ],
  confusable_words: [],
  generated_at: "2026-03-21T00:00:00Z",
  snapshot_id: `snapshot-${runId}`,
});

test("@smoke admin can launch final import from Lexicon Ops and verify in DB Inspector", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-ops-import-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const normalized = `opsimport${uniqueSuffix.replace(/[^0-9a-z]/gi, "").toLowerCase()}`;
  const snapshotName = `ops-import-${normalized}`;
  const hostSnapshotDir = path.join(process.cwd(), "..", "data", "lexicon", "snapshots", snapshotName);
  const reviewedHostDir = path.join(hostSnapshotDir, "reviewed");
  const compiledHostPath = path.join(hostSnapshotDir, "words.enriched.jsonl");
  const approvedHostPath = path.join(reviewedHostDir, "approved.jsonl");

  await rm(hostSnapshotDir, { recursive: true, force: true });
  await mkdir(hostSnapshotDir, { recursive: true });
  await mkdir(reviewedHostDir, { recursive: true });
  const row = `${JSON.stringify(buildCompiledWordRow(uniqueSuffix, normalized))}\n`;
  await writeFile(compiledHostPath, row, "utf-8");
  await writeFile(approvedHostPath, row, "utf-8");

  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/lexicon/ops`);
  await expect(page.getByTestId("lexicon-ops-page")).toBeVisible();

  await page.getByTestId(`lexicon-ops-snapshot-${snapshotName}`).click();
  await expect(page.getByTestId("lexicon-ops-open-import-db")).toBeVisible();
  await page.getByTestId("lexicon-ops-open-import-db").click();

  await expect(page).toHaveURL(/\/lexicon\/import-db/);
  await expect(page.getByTestId("lexicon-import-db-input-path")).toHaveValue(new RegExp(`${snapshotName}/reviewed/approved\\.jsonl$`));

  await page.getByTestId("lexicon-import-db-dry-run-button").click();
  await expect(page.getByText("Import dry-run complete.")).toBeVisible();
  await expect(page.getByTestId("lexicon-import-db-summary-rows")).toContainText("Rows");
  await expect(page.getByTestId("lexicon-import-db-summary-rows")).toContainText("1");

  await page.getByTestId("lexicon-import-db-run-button").click();
  await expect(page.getByText("Import completed.")).toBeVisible();

  await page.goto(`${adminUrl}/lexicon/db-inspector`);
  await page.getByTestId("lexicon-db-inspector-search-input").fill(normalized);
  await page.getByTestId("lexicon-db-inspector-search-button").click();
  await expect(page.getByRole("button", { name: new RegExp(`^${normalized}\\b`) })).toBeVisible();
  await expect(page.getByRole("heading", { name: normalized })).toBeVisible();

  const searchResponse = await request.get(`${apiUrl}/words/search?q=${normalized}`, {
    headers: authHeaders(user.token),
  });
  expect(searchResponse.ok()).toBeTruthy();
  const searchRows = (await searchResponse.json()) as Array<{ id: string }>;
  expect(searchRows.length).toBeGreaterThan(0);

  const enrichmentResponse = await request.get(`${apiUrl}/words/${searchRows[0].id}/enrichment`, {
    headers: authHeaders(user.token),
  });
  expect(enrichmentResponse.ok()).toBeTruthy();
  const enrichment = (await enrichmentResponse.json()) as {
    phonetics: {
      us: { ipa: string; confidence: number };
      uk: { ipa: string; confidence: number };
      au: { ipa: string; confidence: number };
    } | null;
  };
  expect(enrichment.phonetics?.us.ipa).toBe(`/${normalized}/`);
  expect(enrichment.phonetics?.uk.confidence).toBe(0.98);
  expect(enrichment.phonetics?.au.confidence).toBe(0.97);

  await rm(hostSnapshotDir, { recursive: true, force: true });
});
