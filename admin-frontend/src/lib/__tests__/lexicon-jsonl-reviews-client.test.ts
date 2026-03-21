import { apiClient } from "@/lib/api-client";
import {
  loadLexiconJsonlReviewSession,
  materializeLexiconJsonlReviewOutputs,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: { get: jest.fn(), post: jest.fn(), patch: jest.fn() },
}));

describe("admin lexicon-jsonl-reviews-client", () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads a JSONL review session", async () => {
    mockApiClient.post.mockResolvedValueOnce({ artifact_filename: "words.enriched.jsonl" } as any);
    await loadLexiconJsonlReviewSession({ artifactPath: "/tmp/words.enriched.jsonl", decisionsPath: "/tmp/review.decisions.jsonl" });
    expect(mockApiClient.post).toHaveBeenCalledWith("/lexicon-jsonl-reviews/load", {
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/review.decisions.jsonl",
    });
  });

  it("updates an item decision and materializes outputs", async () => {
    mockApiClient.patch.mockResolvedValueOnce({ entry_id: "word:bank", review_status: "approved" } as any);
    mockApiClient.post.mockResolvedValueOnce({ approved_count: 1 } as any);

    await updateLexiconJsonlReviewItem("word:bank", {
      artifactPath: "/tmp/words.enriched.jsonl",
      decisionsPath: "/tmp/review.decisions.jsonl",
      reviewStatus: "approved",
      decisionReason: "ready",
    });
    await materializeLexiconJsonlReviewOutputs({
      artifactPath: "/tmp/words.enriched.jsonl",
      decisionsPath: "/tmp/review.decisions.jsonl",
      outputDir: "/tmp/materialized",
    });

    expect(mockApiClient.patch).toHaveBeenCalledWith("/lexicon-jsonl-reviews/items/word%3Abank", {
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/review.decisions.jsonl",
      review_status: "approved",
      decision_reason: "ready",
    });
    expect(mockApiClient.post).toHaveBeenLastCalledWith("/lexicon-jsonl-reviews/materialize", {
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/review.decisions.jsonl",
      output_dir: "/tmp/materialized",
    });
  });
});
