import { apiClient } from "@/lib/api-client";
import {
  listLexiconReviewBatches,
  listLexiconReviewItems,
  previewLexiconReviewBatchPublish,
  publishLexiconReviewBatch,
  updateLexiconReviewItem,
} from "@/lib/lexicon-reviews-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: { get: jest.fn(), post: jest.fn(), patch: jest.fn() },
}));

describe("admin lexicon-reviews-client", () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;
  beforeEach(() => { jest.clearAllMocks(); });

  it("loads lexicon review batches", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "batch-1", status: "reviewing" }] as any);
    const result = await listLexiconReviewBatches();
    expect(result).toEqual([{ id: "batch-1", status: "reviewing" }]);
    expect(mockApiClient.get).toHaveBeenCalledWith("/lexicon-reviews/batches");
  });

  it("loads batch items with query filters", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "item-1", lemma: "run" }] as any);
    await listLexiconReviewItems("batch-1", { reviewStatus: "pending", reviewRequired: true, riskBand: "rerank_and_review_candidate" });
    expect(mockApiClient.get).toHaveBeenCalledWith("/lexicon-reviews/batches/batch-1/items?review_status=pending&review_required=true&risk_band=rerank_and_review_candidate");
  });

  it("updates a review item", async () => {
    mockApiClient.patch.mockResolvedValueOnce({ id: "item-1", review_status: "approved" } as any);
    const result = await updateLexiconReviewItem("item-1", { review_status: "approved", review_comment: "looks good", review_override_wn_synset_ids: ["run.v.01"] });
    expect(result.review_status).toBe("approved");
  });

  it("loads publish preview and publishes batch", async () => {
    mockApiClient.get.mockResolvedValueOnce({ batch_id: "batch-1", publishable_item_count: 2 } as any);
    mockApiClient.post.mockResolvedValueOnce({ batch_id: "batch-1", status: "published" } as any);
    const preview = await previewLexiconReviewBatchPublish("batch-1");
    const publish = await publishLexiconReviewBatch("batch-1");
    expect(preview.publishable_item_count).toBe(2);
    expect(publish.status).toBe("published");
  });
});
