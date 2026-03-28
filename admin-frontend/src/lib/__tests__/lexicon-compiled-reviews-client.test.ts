import { apiClient } from "@/lib/api-client";
import {
  deleteLexiconCompiledReviewBatch,
  downloadCompiledReviewDecisionsExport,
  downloadApprovedCompiledReviewExport,
  listLexiconCompiledReviewBatches,
  listLexiconCompiledReviewItems,
  updateLexiconCompiledReviewItem,
} from "@/lib/lexicon-compiled-reviews-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

describe("admin lexicon-compiled-reviews-client", () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      text: async () => "{\"entry_id\":\"word:bank\"}\n",
    } as Response);
  });

  it("loads compiled review batches", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "batch-1" }] as any);
    await listLexiconCompiledReviewBatches();
    expect(mockApiClient.get).toHaveBeenCalledWith("/lexicon-compiled-reviews/batches");
  });

  it("loads compiled review items and updates a decision", async () => {
    mockApiClient.get.mockResolvedValueOnce({ items: [{ id: "item-1" }], total: 1, limit: 50, offset: 0, has_more: false } as any);
    mockApiClient.patch.mockResolvedValueOnce({ id: "item-1", review_status: "approved" } as any);
    await listLexiconCompiledReviewItems("batch-1", { limit: 25, offset: 50, reviewStatus: "approved", search: "bank" });
    await updateLexiconCompiledReviewItem("item-1", { review_status: "approved", decision_reason: "ready" });
    expect(mockApiClient.get).toHaveBeenCalledWith("/lexicon-compiled-reviews/batches/batch-1/items?limit=25&offset=50&status=approved&search=bank");
    expect(mockApiClient.patch).toHaveBeenCalledWith("/lexicon-compiled-reviews/items/item-1", { review_status: "approved", decision_reason: "ready" });
  });

  it("deletes a compiled review batch", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await deleteLexiconCompiledReviewBatch("batch-1");
    expect(mockApiClient.delete).toHaveBeenCalledWith("/lexicon-compiled-reviews/batches/batch-1");
  });

  it("downloads approved export text", async () => {
    const text = await downloadApprovedCompiledReviewExport("batch-1");
    expect(text).toContain("word:bank");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/lexicon-compiled-reviews/batches/batch-1/export/approved"),
      expect.objectContaining({ headers: { Authorization: "Bearer active-token" } }),
    );
  });

  it("downloads decisions export text", async () => {
    const text = await downloadCompiledReviewDecisionsExport("batch-1");
    expect(text).toContain("word:bank");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/lexicon-compiled-reviews/batches/batch-1/export/decisions"),
      expect.objectContaining({ headers: { Authorization: "Bearer active-token" } }),
    );
  });
});
