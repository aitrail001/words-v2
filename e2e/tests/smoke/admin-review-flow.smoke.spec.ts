import { expect, test } from "@playwright/test";
import {
  apiUrl,
  authHeaders,
  injectAdminToken,
  registerAdminViaApi,
} from "../helpers/auth";

type ReviewBatch = {
  id: string;
  source_reference: string | null;
  status: string;
};

type ReviewItem = {
  id: string;
  lemma: string;
  review_status: string;
  review_comment: string | null;
  review_override_wn_synset_ids: string[] | null;
};

type PublishPreview = {
  batch_id: string;
  publishable_item_count: number;
  created_word_count: number;
  created_meaning_count: number;
  items: Array<{
    item_id: string;
    lemma: string;
    action: string;
    selected_synset_ids: string[];
  }>;
};

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

const buildSelectionDecisionRow = (runId: string, lemma: string) => ({
  schema_version: "lexicon_selection_decision.v1",
  snapshot_id: `snapshot-${runId}`,
  lexeme_id: `lx_${lemma}_${runId}`,
  lemma,
  language: "en",
  risk_band: "rerank_and_review_candidate",
  selection_risk_score: 6,
  deterministic_selected_wn_synset_ids: ["bank.n.01"],
  candidate_metadata: [
    {
      wn_synset_id: "bank.n.01",
      canonical_label: "financial institution",
      canonical_gloss: "a financial institution that accepts deposits",
      part_of_speech: "noun",
      selection_reason: "common concrete noun",
      selection_score: 9.7,
      candidate_flags: ["core_sense"],
    },
  ],
  review_required: true,
  auto_accepted: false,
  generated_at: "2026-03-08T00:00:00Z",
  generation_run_id: runId,
});

test("@smoke admin can import, approve, preview, and publish a staged review item", async ({
  page,
  request,
}) => {
  const user = await registerAdminViaApi(request, "admin-review-smoke");
  const uniqueSuffix = `${Date.now()}-${test.info().workerIndex}`;
  const lemma = `bankword${uniqueSuffix.replace(/[^0-9a-z]/gi, "")}`.toLowerCase();
  const sourceReference = `admin-review-${uniqueSuffix}`;
  const jsonl = `${JSON.stringify(buildSelectionDecisionRow(uniqueSuffix, lemma))}\n`;

  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/lexicon`);
  await expect(page.getByTestId("lexicon-admin-page")).toBeVisible();
  await expect(page.getByTestId("lexicon-admin-title")).toContainText("Lexicon Admin Portal");

  const importResponse = await request.post(`${apiUrl}/lexicon-reviews/batches/import`, {
    headers: { Authorization: `Bearer ${user.token}` },
    multipart: {
      file: {
        name: "selection_decisions.jsonl",
        mimeType: "application/x-ndjson",
        buffer: Buffer.from(jsonl, "utf-8"),
      },
      source_reference: sourceReference,
    },
  });
  expect(importResponse.status()).toBe(201);

  const batchesResponse = await request.get(`${apiUrl}/lexicon-reviews/batches`, {
    headers: authHeaders(user.token),
  });
  expect(batchesResponse.status()).toBe(200);
  const batches = (await batchesResponse.json()) as ReviewBatch[];
  const batch = batches.find((entry) => entry.source_reference === sourceReference);
  expect(batch).toBeTruthy();

  const itemsResponse = await request.get(`${apiUrl}/lexicon-reviews/batches/${batch!.id}/items`, {
    headers: authHeaders(user.token),
  });
  expect(itemsResponse.status()).toBe(200);
  const items = (await itemsResponse.json()) as ReviewItem[];
  expect(items).toHaveLength(1);
  expect(items[0].lemma).toBe(lemma);
  expect(items[0].review_status).toBe("pending");

  await page.goto(`${adminUrl}/lexicon`);
  await expect(page.getByTestId("lexicon-batches-list")).toContainText("selection_decisions.jsonl");
  await expect(page.getByTestId("lexicon-item-detail-panel")).toContainText(`Review item: ${lemma}`);
  await expect(page.getByTestId("lexicon-item-current-selection")).toContainText("Current selected senses");
  await expect(page.getByTestId("lexicon-item-current-selection")).toContainText("bank.n.01");
  await expect(page.getByTestId("lexicon-item-candidates")).toContainText("a financial institution that accepts deposits");
  await expect(page.getByTestId("lexicon-item-candidates")).toContainText("common concrete noun");
  await expect(page.getByTestId("lexicon-item-candidates")).toContainText("core_sense");

  await page.getByTestId("lexicon-item-review-status").selectOption("approved");
  await page.getByTestId("lexicon-item-override-ids").fill("bank.n.01");
  await page.getByTestId("lexicon-item-review-comment").fill("Approved in admin smoke");
  await page.getByTestId("lexicon-item-save-button").click();
  await expect(page.getByTestId("lexicon-item-current-selection")).toContainText("Review override");
  await expect(page.getByTestId("lexicon-item-current-selection")).toContainText("bank.n.01");

  const approvedItemsResponse = await request.get(
    `${apiUrl}/lexicon-reviews/batches/${batch!.id}/items`,
    { headers: authHeaders(user.token) },
  );
  expect(approvedItemsResponse.status()).toBe(200);
  const approvedItems = (await approvedItemsResponse.json()) as ReviewItem[];
  expect(approvedItems).toHaveLength(1);
  const approvedItem = approvedItems[0];
  expect(approvedItem.review_status).toBe("approved");
  expect(approvedItem.review_comment).toBe("Approved in admin smoke");
  expect(approvedItem.review_override_wn_synset_ids).toEqual(["bank.n.01"]);

  await page.getByTestId("lexicon-publish-preview-button").click();
  await expect(page.getByTestId("lexicon-publish-preview-panel")).toBeVisible();
  await expect(page.getByTestId("lexicon-publish-preview-panel")).toContainText("Publishable: 1");
  await expect(page.getByTestId("lexicon-publish-preview-panel")).toContainText(lemma);
  await expect(page.getByTestId("lexicon-publish-preview-panel")).toContainText("bank.n.01");

  const previewResponse = await request.get(
    `${apiUrl}/lexicon-reviews/batches/${batch!.id}/publish-preview`,
    { headers: authHeaders(user.token) },
  );
  expect(previewResponse.status()).toBe(200);
  const preview = (await previewResponse.json()) as PublishPreview;
  expect(preview.batch_id).toBe(batch!.id);
  expect(preview.publishable_item_count).toBe(1);
  expect(preview.created_word_count).toBe(1);
  expect(preview.created_meaning_count).toBeGreaterThanOrEqual(1);
  expect(preview.items).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        lemma,
        selected_synset_ids: ["bank.n.01"],
      }),
    ]),
  );

  await page.getByTestId("lexicon-publish-button").click();
  await expect(page.getByText(/Published 1 items to 1 words\./i)).toBeVisible();

  const publishedBatchResponse = await request.get(`${apiUrl}/lexicon-reviews/batches`, {
    headers: authHeaders(user.token),
  });
  expect(publishedBatchResponse.status()).toBe(200);
  const publishedBatches = (await publishedBatchResponse.json()) as ReviewBatch[];
  const publishedBatch = publishedBatches.find((entry) => entry.id === batch!.id);
  expect(publishedBatch?.status).toBe("published");

  const wordsResponse = await request.get(
    `${apiUrl}/words/search?q=${encodeURIComponent(lemma)}`,
    { headers: authHeaders(user.token) },
  );
  expect(wordsResponse.status()).toBe(200);
  const words = (await wordsResponse.json()) as Array<{ word: string }>;
  expect(words.some((entry) => entry.word === lemma)).toBe(true);
});
