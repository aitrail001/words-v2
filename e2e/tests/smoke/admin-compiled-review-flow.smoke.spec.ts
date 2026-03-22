import { expect, test } from "@playwright/test";
import {
  apiUrl,
  authHeaders,
  registerAdminViaApi,
} from "../helpers/auth";

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
  const sourceReference = `compiled-review-${uniqueSuffix}`;
  const jsonl = `${JSON.stringify(buildCompiledWordRow(uniqueSuffix, normalized))}\n${JSON.stringify(buildCompiledWordRow(`${uniqueSuffix}-2`, secondary))}\n`;

  const importResponse = await request.post(`${apiUrl}/lexicon-compiled-reviews/batches/import`, {
    headers: { Authorization: `Bearer ${user.token}` },
    multipart: {
      file: {
        name: "words.enriched.jsonl",
        mimeType: "application/x-ndjson",
        buffer: Buffer.from(jsonl, "utf-8"),
      },
      source_reference: sourceReference,
    },
  });
  expect(importResponse.status()).toBe(201);

  const batchesResponse = await request.get(`${apiUrl}/lexicon-compiled-reviews/batches`, {
    headers: authHeaders(user.token),
  });
  expect(batchesResponse.status()).toBe(200);
  const batches = (await batchesResponse.json()) as CompiledReviewBatch[];
  const batch = batches.find((entry) => entry.source_reference === sourceReference);
  expect(batch).toBeTruthy();

  await page.goto(`${adminUrl}/login`);
  await page.getByTestId("login-email-input").fill(user.email);
  await page.getByTestId("login-password-input").fill(user.password);
  await page.getByTestId("login-submit-button").click();
  await expect(page).toHaveURL(`${adminUrl}/`);

  await page.goto(`${adminUrl}/lexicon/compiled-review`);
  await expect(page.getByTestId("lexicon-compiled-review-page")).toBeVisible();
  await expect(page.getByTestId("compiled-review-batches-list")).toContainText("words.enriched.jsonl");
  await expect(page.getByTestId("compiled-review-item-title")).toContainText(normalized);
  await expect(page.getByTestId("compiled-review-items-list")).toContainText("pending");
  await page.getByTestId("compiled-review-decision-reason").fill("approved in compiled review smoke");
  await page.getByTestId("compiled-review-approve-button").click();
  await page.getByTestId("compiled-review-confirm-approved-button").click();
  await expect(page.getByText(new RegExp(`Updated word:${normalized}:${uniqueSuffix} to approved\\.`))).toBeVisible();
  await expect(page.getByTestId("compiled-review-item-title")).toContainText(secondary);

  const itemsResponse = await request.get(`${apiUrl}/lexicon-compiled-reviews/batches/${batch!.id}/items`, {
    headers: authHeaders(user.token),
  });
  expect(itemsResponse.status()).toBe(200);
  const items = (await itemsResponse.json()) as CompiledReviewItem[];
  expect(items).toHaveLength(2);
  const approvedItem = items.find((item) => item.entry_id === `word:${normalized}:${uniqueSuffix}`);
  const pendingItem = items.find((item) => item.entry_id === `word:${secondary}:${uniqueSuffix}-2`);
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
});
