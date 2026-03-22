import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconDbInspectorPage from "@/app/lexicon/db-inspector/page";
import { getWordEnrichmentDetail, searchWords } from "@/lib/words-client";

jest.mock("@/lib/words-client", () => ({
  searchWords: jest.fn(),
  getWordEnrichmentDetail: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconDbInspectorPage", () => {
  const mockSearchWords = searchWords as jest.Mock;
  const mockGetWordEnrichmentDetail = getWordEnrichmentDetail as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchWords.mockResolvedValue([{ id: "word-1", word: "bank", language: "en", phonetic: "bæŋk", frequency_rank: 100 }]);
    mockGetWordEnrichmentDetail.mockResolvedValue({
      id: "word-1",
      word: "bank",
      language: "en",
      phonetic: "bæŋk",
      frequency_rank: 100,
      phonetic_source: "lexicon_snapshot",
      phonetic_confidence: 0.9,
      phonetic_enrichment_run_id: "run-1",
      cefr_level: "B1",
      part_of_speech: ["noun"],
      confusable_words: [],
      learner_generated_at: "2026-03-21T00:00:00Z",
      meanings: [],
      enrichment_runs: [],
    });
  });

  it("renders the standalone DB inspector search flow", async () => {
    const user = userEvent.setup();
    render(<LexiconDbInspectorPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-db-inspector-page")).toBeInTheDocument());
    await user.type(screen.getByTestId("lexicon-db-inspector-search-input"), "bank");
    await user.click(screen.getByTestId("lexicon-db-inspector-search-button"));

    await waitFor(() => expect(mockSearchWords).toHaveBeenCalledWith("bank"));
    await waitFor(() => expect(mockGetWordEnrichmentDetail).toHaveBeenCalledWith("word-1"));
  });
});
