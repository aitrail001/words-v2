import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconWordsPage from "@/app/lexicon/words/page";
import { getWordEnrichmentDetail, searchWords } from "@/lib/words-client";

jest.mock("@/lib/words-client", () => ({
  getWordEnrichmentDetail: jest.fn(),
  searchWords: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

const wordDetail = {
  id: "word-1",
  word: "bank",
  language: "en",
  phonetic: "bæŋk",
  frequency_rank: 100,
  phonetic_source: "llm",
  phonetic_confidence: 0.9,
  phonetic_enrichment_run_id: "run-phonetic",
  cefr_level: "B1",
  part_of_speech: ["noun", "verb"],
  confusable_words: [{ word: "bench", reason: "sound" }],
  learner_generated_at: "2026-03-09T00:00:00Z",
  word_forms: { plural: ["banks"], verb: ["banked", "banking"] },
  source_type: "lexicon_snapshot",
  source_reference: "snapshot-1",
  created_at: "2026-03-09T00:00:00Z",
  meanings: [
    {
      id: "meaning-1",
      definition: "a financial institution",
      part_of_speech: "noun",
      example_sentence: null,
      order_index: 0,
      wn_synset_id: "bank.n.01",
      primary_domain: "finance",
      secondary_domains: ["money"],
      register: null,
      grammar_patterns: [],
      usage_note: "Common everyday use",
      learner_generated_at: "2026-03-09T00:00:00Z",
      source: "lexicon_snapshot",
      source_reference: "snapshot-1:bank.n.01",
      created_at: "2026-03-09T00:00:00Z",
      translations: [{ id: "translation-1", language: "es", translation: "banco" }],
      examples: [
        {
          id: "example-1",
          sentence: "She went to the bank after work.",
          difficulty: "easy",
          order_index: 0,
          source: "llm",
          confidence: 0.8,
          enrichment_run_id: "run-1",
        },
      ],
      relations: [],
    },
  ],
  enrichment_runs: [
    {
      id: "run-1",
      enrichment_job_id: "job-1",
      generator_provider: "openai",
      generator_model: "gpt-5.1",
      validator_provider: null,
      validator_model: null,
      prompt_version: "v1",
      prompt_hash: "hash",
      verdict: "accepted",
      confidence: 0.88,
      token_input: 100,
      token_output: 50,
      estimated_cost: 0.01,
      created_at: "2026-03-09T00:00:00Z",
    },
  ],
};

describe("LexiconWordsPage", () => {
  const mockSearchWords = searchWords as jest.Mock;
  const mockGetWordEnrichmentDetail = getWordEnrichmentDetail as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchWords.mockResolvedValue([
      { id: "word-1", word: "bank", language: "en", phonetic: null, frequency_rank: 100 },
    ]);
    mockGetWordEnrichmentDetail.mockResolvedValue(wordDetail);
  });

  it("searches the local db and renders the full word record", async () => {
    const user = userEvent.setup();
    render(<LexiconWordsPage />);

    await user.type(screen.getByTestId("lexicon-words-search-input"), "bank");
    await user.click(screen.getByTestId("lexicon-words-search-button"));

    await waitFor(() => expect(mockSearchWords).toHaveBeenCalledWith("bank"));
    await waitFor(() => expect(mockGetWordEnrichmentDetail).toHaveBeenCalledWith("word-1"));

    expect(screen.getByTestId("lexicon-words-detail-panel")).toHaveTextContent("Source reference");
    expect(screen.getByTestId("lexicon-words-detail-panel")).toHaveTextContent("snapshot-1");
    expect(screen.getByTestId("lexicon-words-detail-panel")).toHaveTextContent("banks");
    expect(screen.getByTestId("lexicon-words-detail-panel")).toHaveTextContent("banco");
    expect(screen.getByTestId("lexicon-words-detail-panel")).toHaveTextContent("a financial institution");
  });
});
