import { expect, test } from "@playwright/test";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  apiUrl,
  authHeaders,
  injectAdminToken,
  registerAdminViaApi,
  waitForAppReady,
} from "../helpers/auth";
import { selectCompiledReviewBatch } from "../helpers/compiled-review";

type CompiledReviewBatch = {
  id: string;
  artifact_filename: string;
  source_reference: string | null;
};

type CompiledReviewItem = {
  id: string;
  entry_id: string;
  review_status: string;
  decision_reason: string | null;
  import_eligible: boolean;
  regen_requested: boolean;
};

type CompiledReviewItemsPage = {
  items: CompiledReviewItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";
const dataRoot = process.env.E2E_WORDS_DATA_ROOT ?? process.env.WORDS_DATA_DIR ?? "/app/data";

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
        "zh-Hans": {
          definition: `${word} 的定义`,
          usage_note: "常见义项",
          examples: [`这个${word}很明显。`],
        },
        es: {
          definition: `definicion de ${word}`,
          usage_note: "uso comun",
          examples: [`El ${word} es visible.`],
        },
        ar: {
          definition: `تعريف ${word}`,
          usage_note: "معنى شائع",
          examples: [`هذا ${word} واضح.`],
        },
        "pt-BR": {
          definition: `definicao de ${word}`,
          usage_note: "uso comum",
          examples: [`O ${word} esta visivel.`],
        },
        ja: {
          definition: `${word} の定義`,
          usage_note: "よくある意味",
          examples: [`その${word}が見える。`],
        },
      },
    },
  ],
  confusable_words: [],
  generated_at: "2026-03-21T00:00:00Z",
});

test("@smoke admin can review and export a compiled lexicon batch", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-compiled-review-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const normalized = `artifact${uniqueSuffix.replace(/[^0-9a-z]/gi, "").toLowerCase()}`;
  const secondary = `${normalized}harbor`;
  const snapshotName = `compiled-review-${normalized}`;
  const hostSnapshotDir = path.join(dataRoot, "lexicon", "snapshots", snapshotName);
  const reviewedHostDir = path.join(hostSnapshotDir, "reviewed");
  const approvedHostPath = path.join(reviewedHostDir, "approved.jsonl");
  const decisionsHostPath = path.join(reviewedHostDir, "review.decisions.jsonl");
  const backendDataRoot = process.env.E2E_WORDS_DATA_ROOT ?? process.env.WORDS_DATA_DIR ?? "/app/data";
  const backendApprovedPath = `${backendDataRoot}/lexicon/snapshots/${snapshotName}/reviewed/approved.jsonl`;
  const jsonl = `${JSON.stringify(buildCompiledWordRow(uniqueSuffix, normalized))}\n${JSON.stringify(buildCompiledWordRow(`${uniqueSuffix}-2`, secondary))}\n`;

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

  await page.goto(`${adminUrl}/lexicon/compiled-review`);
  await expect(page.getByTestId("lexicon-compiled-review-page")).toBeVisible();
  await selectCompiledReviewBatch(page, snapshotName);
  await expect(page.getByTestId("compiled-review-batches-list")).toContainText(snapshotName);
  await expect(page.getByTestId("compiled-review-item-title")).toContainText(normalized);
  await expect(page.getByTestId("compiled-review-items-list")).toContainText("pending");
  await page.getByTestId("compiled-review-decision-reason").fill("approved in compiled review smoke");
  await page.getByTestId("compiled-review-approve-button").click();
  await expect(page.getByText(new RegExp(`Updated word:${normalized}:${uniqueSuffix} to approved\\.`))).toBeVisible();
  await expect(page.getByTestId("compiled-review-item-title")).toContainText(secondary);

  const itemsResponse = await request.get(`${apiUrl}/lexicon-compiled-reviews/batches/${batch!.id}/items`, {
    headers: authHeaders(user.token),
  });
  expect(itemsResponse.status()).toBe(200);
  const itemsPage = (await itemsResponse.json()) as CompiledReviewItemsPage;
  expect(itemsPage.total).toBe(2);
  expect(itemsPage.items).toHaveLength(2);
  const approvedItem = itemsPage.items.find((item) => item.entry_id === `word:${normalized}:${uniqueSuffix}`);
  const pendingItem = itemsPage.items.find((item) => item.entry_id === `word:${secondary}:${uniqueSuffix}-2`);
  expect(approvedItem?.review_status).toBe("approved");
  expect(approvedItem?.decision_reason).toBe("approved in compiled review smoke");
  expect(approvedItem?.import_eligible).toBe(true);
  expect(approvedItem?.regen_requested).toBe(false);
  expect(pendingItem?.review_status).toBe("pending");

  const decisionDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download Decision Ledger" }).click();
  const downloaded = await decisionDownload;
  expect(downloaded.suggestedFilename()).toContain(".decisions.jsonl");

  const decisionExportResponse = await request.get(
    `${apiUrl}/lexicon-compiled-reviews/batches/${batch!.id}/export/decisions`,
    { headers: authHeaders(user.token) },
  );
  expect(decisionExportResponse.status()).toBe(200);
  const decisionLines = (await decisionExportResponse.text()).split("\n").filter(Boolean).map((line) => JSON.parse(line) as {
    entry_id: string;
    decision: string;
    decision_reason: string | null;
  });
  expect(decisionLines).toEqual([
    expect.objectContaining({
      entry_id: `word:${normalized}:${uniqueSuffix}`,
      decision: "approved",
      decision_reason: "approved in compiled review smoke",
    }),
  ]);

  const approvedExportResponse = await request.get(
    `${apiUrl}/lexicon-compiled-reviews/batches/${batch!.id}/export/approved`,
    { headers: authHeaders(user.token) },
  );
  expect(approvedExportResponse.status()).toBe(200);
  const approvedLines = (await approvedExportResponse.text()).split("\n").filter(Boolean).map((line) => JSON.parse(line) as {
    entry_id: string;
  });
  expect(approvedLines).toEqual([
    expect.objectContaining({
      entry_id: `word:${normalized}:${uniqueSuffix}`,
    }),
  ]);

  await page.getByRole("button", { name: "Materialize Reviewed Outputs" }).click();
  await expect(page.getByText(backendApprovedPath)).toBeVisible();
  await expect
    .poll(
      async () => {
        try {
          await readFile(approvedHostPath, "utf-8");
          return true;
        } catch {
          return false;
        }
      },
      {
        timeout: 15_000,
        intervals: [250, 500, 1_000],
      },
    )
    .toBe(true);
  const approvedMaterialized = (await readFile(approvedHostPath, "utf-8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { entry_id: string });
  expect(approvedMaterialized).toEqual([
    expect.objectContaining({ entry_id: `word:${normalized}:${uniqueSuffix}` }),
  ]);
  const decisionMaterialized = (await readFile(decisionsHostPath, "utf-8"))
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as { entry_id: string; decision: string });
  expect(decisionMaterialized).toEqual([
    expect.objectContaining({ entry_id: `word:${normalized}:${uniqueSuffix}`, decision: "approved" }),
  ]);

  await page.getByRole("button", { name: "Delete Batch" }).click();
  await page.getByRole("button", { name: "Confirm Delete Batch" }).click();
  await expect(page.getByText("Deleted words.enriched.jsonl.")).toBeVisible();
  await rm(hostSnapshotDir, { recursive: true, force: true });
});
