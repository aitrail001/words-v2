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

type PublishResult = {
  batch_id: string;
  status: string;
  published_item_count: number;
  published_word_count: number;
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

  const approveResponse = await request.patch(`${apiUrl}/lexicon-reviews/items/${items[0].id}`, {
    headers: authHeaders(user.token),
    data: {
      review_status: "approved",
      review_comment: "Approved in admin smoke",
      review_override_wn_synset_ids: ["bank.n.01"],
    },
  });
  expect(approveResponse.status()).toBe(200);
  const approvedItem = (await approveResponse.json()) as ReviewItem;
  expect(approvedItem.review_status).toBe("approved");
  expect(approvedItem.review_comment).toBe("Approved in admin smoke");
  expect(approvedItem.review_override_wn_synset_ids).toEqual(["bank.n.01"]);

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

  if (preview.publishable_item_count > 0) {
    const publishResponse = await request.post(
      `${apiUrl}/lexicon-reviews/batches/${batch!.id}/publish`,
      { headers: authHeaders(user.token) },
    );
    expect(publishResponse.status()).toBe(200);
    const publishResult = (await publishResponse.json()) as PublishResult;
    expect(publishResult.batch_id).toBe(batch!.id);
    expect(publishResult.status).toBe("published");
    expect(publishResult.published_item_count).toBe(1);
    expect(publishResult.published_word_count).toBe(1);

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
  }
});
