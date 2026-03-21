import { render, screen, waitFor } from "@testing-library/react";
import LexiconLegacyPage from "@/app/lexicon/legacy/page";

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

jest.mock("@/lib/lexicon-reviews-client", () => ({
  getLexiconReviewBatch: jest.fn().mockResolvedValue(null),
  importLexiconReviewBatch: jest.fn(),
  listLexiconReviewBatches: jest.fn().mockResolvedValue([]),
  listLexiconReviewItems: jest.fn().mockResolvedValue([]),
  previewLexiconReviewBatchPublish: jest.fn(),
  publishLexiconReviewBatch: jest.fn(),
  updateLexiconReviewItem: jest.fn(),
}));

jest.mock("@/lib/words-client", () => ({
  getWordEnrichmentDetail: jest.fn(),
  searchWords: jest.fn(),
}));

describe("LexiconLegacyPage", () => {
  it("marks the old staged review workflow as legacy", async () => {
    render(<LexiconLegacyPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-legacy-page")).toBeInTheDocument());
    expect(screen.getByText(/legacy/i)).toBeInTheDocument();
    expect(screen.getByText(/selection review/i)).toBeInTheDocument();
  });
});
