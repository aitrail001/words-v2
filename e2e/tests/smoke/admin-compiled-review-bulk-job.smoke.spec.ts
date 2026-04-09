import { expect, test } from "@playwright/test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  apiUrl,
  authHeaders,
  injectAdminToken,
  registerAdminViaApi,
  waitForAppReady,
} from "../helpers/auth";
import { selectCompiledReviewBatch } from "../helpers/compiled-review";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

type CompiledReviewBatch = {
  id: string;
  source_reference: string | null;
  approved_count: number;
  pending_count: number;
};

type CompiledReviewItemsPage = {
  items: Array<{
    entry_id: string;
    review_status: string;
    decision_reason: string | null;
    import_eligible: boolean;
  }>;
  total: number;
};

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
      examples: [{ sentence: `The ${word} is visible.`, difficulty: "A1" }],
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
});

test("@smoke admin can bulk approve a compiled lexicon batch with progress", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-compiled-review-bulk");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const base = `bulkartifact${uniqueSuffix.replace(/[^0-9a-z]/gi, "").toLowerCase()}`;
  const snapshotName = `compiled-review-bulk-${base}`;
  const hostSnapshotDir = path.join(process.cwd(), "..", "data", "lexicon", "snapshots", snapshotName);
  const words = [`${base}one`, `${base}two`, `${base}three`];
  const jsonl = words.map((word, index) => JSON.stringify(buildCompiledWordRow(`${uniqueSuffix}-${index + 1}`, word))).join("\n") + "\n";

  await rm(hostSnapshotDir, { recursive: true, force: true });
  await mkdir(hostSnapshotDir, { recursive: true });
  await writeFile(path.join(hostSnapshotDir, "words.enriched.jsonl"), jsonl, "utf-8");

  const importResponse = await request.post(`${apiUrl}/lexicon-compiled-reviews/batches/import`, {
    headers: { Authorization: `Bearer ${user.token}` },
    multipart: {
      file: {
        name: "words.enriched.jsonl",
        mimeType: "application/x-ndjson",
        buffer: Buffer.from(jsonl, "utf-8"),
      },
      source_reference: snapshotName,
    },
  });
  expect(importResponse.status()).toBe(201);

  const batchesResponse = await request.get(`${apiUrl}/lexicon-compiled-reviews/batches`, {
    headers: authHeaders(user.token),
  });
  expect(batchesResponse.status()).toBe(200);
  const batches = (await batchesResponse.json()) as CompiledReviewBatch[];
  const batch = batches.find((entry) => entry.source_reference === snapshotName);
  expect(batch).toBeTruthy();

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/`);
  await expect(page).toHaveURL(`${adminUrl}/`);

  await page.goto(`${adminUrl}/lexicon/compiled-review?sourceReference=${encodeURIComponent(snapshotName)}`);
  await expect(page.getByTestId("lexicon-compiled-review-page")).toBeVisible();
  await selectCompiledReviewBatch(page, snapshotName);
  await expect(page.getByTestId("compiled-review-item-title")).toContainText(words[0]);
  await page.getByTestId("compiled-review-decision-reason").fill("bulk approved in smoke");
  await page.getByTestId("compiled-review-approve-all-button").click();
  await page.getByTestId("compiled-review-confirm-bulk-approved-button").click();

  await expect(page.getByTestId("compiled-review-bulk-job-progress")).toBeVisible();
  await expect(page.getByText(/Completed bulk approved job for 3 rows\./i)).toBeVisible({ timeout: 20_000 });

  const updatedBatchesResponse = await request.get(`${apiUrl}/lexicon-compiled-reviews/batches`, {
    headers: authHeaders(user.token),
  });
  expect(updatedBatchesResponse.status()).toBe(200);
  const updatedBatches = (await updatedBatchesResponse.json()) as CompiledReviewBatch[];
  const updatedBatch = updatedBatches.find((entry) => entry.source_reference === snapshotName);
  expect(updatedBatch?.approved_count).toBe(3);
  expect(updatedBatch?.pending_count).toBe(0);

  const itemsResponse = await request.get(`${apiUrl}/lexicon-compiled-reviews/batches/${batch!.id}/items`, {
    headers: authHeaders(user.token),
  });
  expect(itemsResponse.status()).toBe(200);
  const itemsPage = (await itemsResponse.json()) as CompiledReviewItemsPage;
  expect(itemsPage.total).toBe(3);
  expect(itemsPage.items.every((item) => item.review_status === "approved")).toBeTruthy();
  expect(itemsPage.items.every((item) => item.decision_reason === "bulk approved in smoke")).toBeTruthy();
  expect(itemsPage.items.every((item) => item.import_eligible)).toBeTruthy();

  await rm(hostSnapshotDir, { recursive: true, force: true });
});
