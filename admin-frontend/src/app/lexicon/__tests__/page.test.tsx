import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconPage from "@/app/lexicon/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";
import {
  getLexiconReviewBatch,
  importLexiconReviewBatch,
  listLexiconReviewBatches,
  listLexiconReviewItems,
  previewLexiconReviewBatchPublish,
  publishLexiconReviewBatch,
  updateLexiconReviewItem,
} from "@/lib/lexicon-reviews-client";
import { getWordEnrichmentDetail, searchWords } from "@/lib/words-client";

jest.mock("@/lib/lexicon-reviews-client", () => ({
  getLexiconReviewBatch: jest.fn(),
  importLexiconReviewBatch: jest.fn(),
  listLexiconReviewBatches: jest.fn(),
  listLexiconReviewItems: jest.fn(),
  previewLexiconReviewBatchPublish: jest.fn(),
  publishLexiconReviewBatch: jest.fn(),
  updateLexiconReviewItem: jest.fn(),
}));

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

const batch = {
  id: "batch-1",
  user_id: "user-1",
  status: "reviewing",
  source_filename: "selection.jsonl",
  source_hash: "hash-1",
  source_type: "lexicon_selection_decisions",
  source_reference: "snapshot-1",
  snapshot_id: "snapshot-1",
  total_items: 2,
  review_required_count: 1,
  auto_accepted_count: 1,
  error_message: null,
  created_at: "2026-03-09T00:00:00Z",
  started_at: "2026-03-09T00:00:00Z",
  completed_at: null,
};

const reviewItem = {
  id: "item-1",
  batch_id: "batch-1",
  lexeme_id: "lexeme-1",
  lemma: "bank",
  language: "en",
  wordfreq_rank: 100,
  risk_band: "rerank_and_review_candidate",
  selection_risk_score: 9,
  deterministic_selected_wn_synset_ids: ["bank.n.01", "bank.v.01"],
  reranked_selected_wn_synset_ids: ["bank.n.01", "bank.n.02"],
  selected_wn_synset_ids: ["bank.n.01", "bank.n.02"],
  selected_source: "reranked",
  candidate_metadata: [
    {
      wn_synset_id: "bank.n.01",
      part_of_speech: "noun",
      canonical_label: "bank",
      canonical_gloss: "a financial institution",
      selection_score: 9.7,
      lemma_count: 12,
      candidate_flags: ["core_sense", "high_frequency"],
      candidate_rank: 2,
      selection_reason: "deterministic kept common money meaning",
    },
    {
      wn_synset_id: "bank.n.02",
      part_of_speech: "noun",
      canonical_label: "bank",
      definition: "sloping land beside a river",
      score: 8.2,
      lemma_count: 9,
      rerank_rank: 1,
      rerank_reason: "reranked higher for learner usefulness",
    },
    {
      wn_synset_id: "bank.v.01",
      part_of_speech: "verb",
      canonical_label: "bank",
      canonical_gloss: "to deposit money",
      selection_score: 7.1,
      lemma_count: 5,
      candidate_flags: ["verb_sense"],
      candidate_rank: 3,
      selection_reason: "verb kept by deterministic selector",
    },
  ],
  candidate_entries: [
    {
      wn_synset_id: "bank.n.01",
      canonical_label: "bank",
      gloss: "a financial institution",
      definition: "a financial institution",
      part_of_speech: "noun",
      rank_hint: 2,
      reason_hint: "deterministic kept common money meaning",
      deterministic_selected: true,
      reranked_selected: true,
      review_override_selected: false,
      selected: true,
    },
    {
      wn_synset_id: "bank.n.02",
      canonical_label: "bank",
      gloss: "sloping land beside a river",
      definition: "sloping land beside a river",
      part_of_speech: "noun",
      rank_hint: 1,
      reason_hint: "reranked higher for learner usefulness",
      deterministic_selected: false,
      reranked_selected: true,
      review_override_selected: false,
      selected: true,
    },
    {
      wn_synset_id: "bank.v.01",
      canonical_label: "bank",
      gloss: "to deposit money",
      definition: "to deposit money",
      part_of_speech: "verb",
      rank_hint: 3,
      reason_hint: "verb kept by deterministic selector",
      deterministic_selected: true,
      reranked_selected: false,
      review_override_selected: false,
      selected: false,
    },
  ],
  auto_accepted: false,
  review_required: true,
  review_status: "pending",
  review_override_wn_synset_ids: null,
  review_comment: null,
  reviewed_by: null,
  reviewed_at: null,
  row_payload: {},
  created_at: "2026-03-09T00:00:00Z",
};

const savedItem = {
  ...reviewItem,
  review_status: "approved",
  review_comment: "Looks good",
  review_override_wn_synset_ids: ["bank.n.01"],
  selected_wn_synset_ids: ["bank.n.01"],
  selected_source: "review_override",
  candidate_entries: [
    {
      ...reviewItem.candidate_entries[0],
      review_override_selected: true,
      selected: true,
    },
    {
      ...reviewItem.candidate_entries[1],
      selected: false,
    },
    reviewItem.candidate_entries[2],
  ],
};

const preview = {
  batch_id: "batch-1",
  publishable_item_count: 1,
  created_word_count: 1,
  updated_word_count: 0,
  replaced_meaning_count: 0,
  created_meaning_count: 2,
  skipped_item_count: 0,
  items: [
    {
      item_id: "item-1",
      lemma: "bank",
      language: "en",
      action: "create",
      selected_synset_ids: ["bank.n.01"],
      existing_lexicon_meaning_count: 0,
      new_meaning_count: 2,
      warnings: [],
    },
  ],
};

const publishResult = {
  batch_id: "batch-1",
  status: "published",
  published_item_count: 1,
  published_word_count: 1,
  updated_word_count: 0,
  replaced_meaning_count: 0,
  created_meaning_count: 2,
  published_at: "2026-03-09T01:00:00Z",
};

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
      examples: [{ id: "example-1", sentence: "She went to the bank after work.", difficulty: "easy", order_index: 0, source: "llm", confidence: 0.8, enrichment_run_id: "run-1" }],
      relations: [],
    },
  ],
  enrichment_runs: [{ id: "run-1", enrichment_job_id: "job-1", generator_provider: "openai", generator_model: "gpt-5.1", validator_provider: null, validator_model: null, prompt_version: "v1", prompt_hash: "hash", verdict: "accepted", confidence: 0.88, token_input: 100, token_output: 50, estimated_cost: 0.01, created_at: "2026-03-09T00:00:00Z" }],
};

describe("LexiconPage", () => {
  const mockGetLexiconReviewBatch = getLexiconReviewBatch as jest.Mock;
  const mockImportLexiconReviewBatch = importLexiconReviewBatch as jest.Mock;
  const mockListLexiconReviewBatches = listLexiconReviewBatches as jest.Mock;
  const mockListLexiconReviewItems = listLexiconReviewItems as jest.Mock;
  const mockPreviewLexiconReviewBatchPublish = previewLexiconReviewBatchPublish as jest.Mock;
  const mockPublishLexiconReviewBatch = publishLexiconReviewBatch as jest.Mock;
  const mockUpdateLexiconReviewItem = updateLexiconReviewItem as jest.Mock;
  const mockSearchWords = searchWords as jest.Mock;
  const mockGetWordEnrichmentDetail = getWordEnrichmentDetail as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockListLexiconReviewBatches.mockResolvedValue([batch]);
    mockGetLexiconReviewBatch.mockResolvedValue(batch);
    mockListLexiconReviewItems.mockResolvedValue([reviewItem]);
    mockPreviewLexiconReviewBatchPublish.mockResolvedValue(preview);
    mockPublishLexiconReviewBatch.mockResolvedValue(publishResult);
    mockUpdateLexiconReviewItem.mockResolvedValue(savedItem);
    mockSearchWords.mockResolvedValue([{ id: "word-1", word: "bank", language: "en", phonetic: null, frequency_rank: 100 }]);
    mockGetWordEnrichmentDetail.mockResolvedValue(wordDetail);
    mockImportLexiconReviewBatch.mockResolvedValue(batch);
  });

  it("loads staged batches and selected review item", async () => {
    render(<LexiconPage />);

    await waitFor(() => {
      expect(mockListLexiconReviewBatches).toHaveBeenCalledTimes(1);
      expect(mockGetLexiconReviewBatch).toHaveBeenCalledWith("batch-1");
      expect(mockListLexiconReviewItems).toHaveBeenCalledWith("batch-1", {});
    });

    expect(screen.getByTestId("lexicon-batches-list")).toHaveTextContent("selection.jsonl");
    expect(screen.getByTestId("lexicon-item-detail-panel")).toHaveTextContent("bank");
    expect(screen.getByTestId("lexicon-item-current-selection")).toHaveTextContent("Current selected senses");
    expect(screen.getByTestId("lexicon-item-current-selection")).toHaveTextContent("Reranked");
    expect(screen.getByTestId("lexicon-item-reranked-selection")).toHaveTextContent("reranked higher for learner usefulness");
    expect(screen.getByTestId("lexicon-item-candidates")).toHaveTextContent("sloping land beside a river");
    expect(screen.getByTestId("lexicon-item-candidates")).toHaveTextContent("Reason hint:");
    expect(screen.getByTestId("lexicon-item-candidates")).toHaveTextContent("core_sense");
  });

  it("imports a staged review batch", async () => {
    const user = userEvent.setup();
    render(<LexiconPage />);

    const file = new File(["{}"], "selection_decisions.jsonl", { type: "application/json" });
    await user.upload(screen.getByTestId("lexicon-review-import-file"), file);
    await user.type(screen.getByTestId("lexicon-review-source-reference"), "stage-3");
    await user.click(screen.getByTestId("lexicon-review-import-submit"));

    await waitFor(() => {
      expect(mockImportLexiconReviewBatch).toHaveBeenCalled();
    });
  });

  it("saves a review decision", async () => {
    const user = userEvent.setup();
    render(<LexiconPage />);

    await screen.findByText("Review item: bank");

    await user.selectOptions(screen.getByTestId("lexicon-item-review-status"), "approved");
    await user.type(screen.getByTestId("lexicon-item-override-ids"), "bank.n.01");
    await user.type(screen.getByTestId("lexicon-item-review-comment"), "Looks good");
    await user.click(screen.getByTestId("lexicon-item-save-button"));

    await waitFor(() => {
      expect(mockUpdateLexiconReviewItem).toHaveBeenCalledWith("item-1", {
        review_status: "approved",
        review_comment: "Looks good",
        review_override_wn_synset_ids: ["bank.n.01"],
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("lexicon-item-current-selection")).toHaveTextContent("Review override");
    });
  });

  it("loads a publish preview and publishes approved items", async () => {
    const user = userEvent.setup();
    render(<LexiconPage />);

    await screen.findByTestId("lexicon-batch-detail-panel");
    await user.click(screen.getByTestId("lexicon-publish-preview-button"));

    await waitFor(() => expect(mockPreviewLexiconReviewBatchPublish).toHaveBeenCalledWith("batch-1"));
    expect(screen.getByTestId("lexicon-publish-preview-panel")).toHaveTextContent("Publishable: 1");

    await user.click(screen.getByTestId("lexicon-publish-button"));
    await waitFor(() => expect(mockPublishLexiconReviewBatch).toHaveBeenCalledWith("batch-1"));
    expect(screen.getByText(/Published 1 items to 1 words/i)).toBeInTheDocument();
  });

  it("searches the local db and shows imported word detail", async () => {
    const user = userEvent.setup();
    render(<LexiconPage />);

    await user.click(screen.getByTestId("lexicon-tab-db"));
    await user.type(screen.getByTestId("lexicon-db-search-input"), "bank");
    await user.click(screen.getByTestId("lexicon-db-search-button"));

    await waitFor(() => expect(mockSearchWords).toHaveBeenCalledWith("bank"));
    await waitFor(() => expect(mockGetWordEnrichmentDetail).toHaveBeenCalledWith("word-1"));
    expect(screen.getByTestId("lexicon-db-word-detail-panel")).toHaveTextContent("a financial institution");
  });
});

describe("Admin auth middleware for /lexicon", () => {
  it("redirects unauthenticated lexicon route requests to /login", () => {
    expect(getAuthRedirectPath("/lexicon", false)).toBe("/login?next=%2Flexicon");
  });

  it("allows authenticated lexicon route requests", () => {
    expect(getAuthRedirectPath("/lexicon", true)).toBeNull();
  });
});
