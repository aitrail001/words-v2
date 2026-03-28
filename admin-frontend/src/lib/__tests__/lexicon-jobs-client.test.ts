import { apiClient } from "@/lib/api-client";
import {
  createCompiledMaterializeLexiconJob,
  createCompiledReviewBulkUpdateLexiconJob,
} from "@/lib/lexicon-jobs-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));

describe("admin lexicon-jobs-client", () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("creates a compiled materialize job", async () => {
    mockApiClient.post.mockResolvedValueOnce({ id: "job-1", job_type: "compiled_materialize" } as any);
    await createCompiledMaterializeLexiconJob({ batchId: "batch-1", outputDir: "/tmp/reviewed" });
    expect(mockApiClient.post).toHaveBeenCalledWith("/lexicon-jobs/compiled-materialize", {
      batch_id: "batch-1",
      output_dir: "/tmp/reviewed",
    });
  });

  it("creates a compiled review bulk update job", async () => {
    mockApiClient.post.mockResolvedValueOnce({ id: "job-2", job_type: "compiled_review_bulk_update" } as any);
    await createCompiledReviewBulkUpdateLexiconJob({
      batchId: "batch-1",
      reviewStatus: "approved",
      decisionReason: "bulk ready",
      scope: "all_pending",
    });
    expect(mockApiClient.post).toHaveBeenCalledWith("/lexicon-jobs/compiled-review-bulk-update", {
      batch_id: "batch-1",
      review_status: "approved",
      decision_reason: "bulk ready",
      scope: "all_pending",
    });
  });
});
