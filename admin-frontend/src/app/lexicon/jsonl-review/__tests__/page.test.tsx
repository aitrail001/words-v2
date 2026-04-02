import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconJsonlReviewPage from "@/app/lexicon/jsonl-review/page";
import {
  bulkUpdateLexiconJsonlReviewItems,
  browseLexiconJsonlReviewItems,
  downloadApprovedLexiconJsonlReviewOutput,
  getLexiconJsonlReviewSession,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";
import {
  createJsonlMaterializeLexiconJob,
  getLexiconJob,
} from "@/lib/lexicon-jobs-client";

jest.mock("@/lib/lexicon-jsonl-reviews-client", () => ({
  bulkUpdateLexiconJsonlReviewItems: jest.fn(),
  browseLexiconJsonlReviewItems: jest.fn(),
  downloadApprovedLexiconJsonlReviewOutput: jest.fn(),
  downloadDecisionLexiconJsonlReviewOutput: jest.fn(),
  downloadRegenerateLexiconJsonlReviewOutput: jest.fn(),
  downloadRejectedLexiconJsonlReviewOutput: jest.fn(),
  getLexiconJsonlReviewSession: jest.fn(),
  updateLexiconJsonlReviewItem: jest.fn(),
}));

jest.mock("@/lib/lexicon-jobs-client", () => ({
  createJsonlMaterializeLexiconJob: jest.fn(),
  getLexiconJob: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconJsonlReviewPage", () => {
  const mockGetSessionSummary = getLexiconJsonlReviewSession as jest.Mock;
  const mockBrowseItems = browseLexiconJsonlReviewItems as jest.Mock;
  const mockUpdateItem = updateLexiconJsonlReviewItem as jest.Mock;
  const mockBulkUpdateItems = bulkUpdateLexiconJsonlReviewItems as jest.Mock;
  const mockMaterialize = createJsonlMaterializeLexiconJob as jest.Mock;
  const mockGetLexiconJob = getLexiconJob as jest.Mock;
  const mockDownloadApproved = downloadApprovedLexiconJsonlReviewOutput as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    URL.createObjectURL = jest.fn(() => "blob:test");
    URL.revokeObjectURL = jest.fn();
    HTMLAnchorElement.prototype.click = jest.fn();
    mockGetSessionSummary.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 3,
      pending_count: 2,
      approved_count: 1,
      rejected_count: 0,
    });
    mockBrowseItems.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 3,
      pending_count: 2,
      approved_count: 1,
      rejected_count: 0,
      filtered_total: 3,
      limit: 25,
      offset: 0,
      has_more: false,
      items: [
        {
          entry_id: "word:bank",
          entry_type: "word",
          normalized_form: "bank",
          display_text: "bank",
          review_priority: "normal",
          warning_count: 0,
          warning_labels: [],
          review_summary: {
            sense_count: 1,
            form_variant_count: 1,
            confusable_count: 0,
            provenance_sources: ["snapshot"],
            primary_definition: "a financial institution",
            primary_example: "She went to the bank.",
          },
          review_status: "approved",
          decision_reason: "ready",
          reviewed_at: "2026-03-21T01:00:00Z",
          compiled_payload: { entry_id: "word:bank", word: "bank" },
        },
        {
          entry_id: "phrase:break-a-leg",
          entry_type: "phrase",
          normalized_form: "break a leg",
          display_text: "break a leg",
          review_priority: "warning",
          warning_count: 2,
          warning_labels: ["missing_source_provenance", "missing_examples"],
          review_summary: {
            sense_count: 1,
            form_variant_count: 0,
            confusable_count: 0,
            provenance_sources: [],
            primary_definition: "good luck",
            primary_example: null,
          },
          review_status: "pending",
          decision_reason: null,
          reviewed_at: null,
          compiled_payload: { entry_id: "phrase:break-a-leg", word: "break a leg" },
        },
        {
          entry_id: "word:harbor",
          entry_type: "word",
          normalized_form: "harbor",
          display_text: "harbor",
          review_priority: "normal",
          warning_count: 0,
          warning_labels: [],
          review_summary: {
            sense_count: 1,
            form_variant_count: 1,
            confusable_count: 0,
            provenance_sources: ["snapshot"],
            primary_definition: "a sheltered body of water",
            primary_example: "The ship reached the harbor.",
          },
          review_status: "pending",
          decision_reason: null,
          reviewed_at: null,
          compiled_payload: { entry_id: "word:harbor", word: "harbor" },
        },
      ],
    });
    mockUpdateItem.mockImplementation(async (entryId: string, payload: { decisionReason: string | null; reviewStatus: string }) => {
      const base =
        entryId === "phrase:break-a-leg"
          ? {
              entry_id: "phrase:break-a-leg",
              entry_type: "phrase",
              normalized_form: "break a leg",
              display_text: "break a leg",
              review_priority: "warning",
              warning_count: 2,
              warning_labels: ["missing_source_provenance", "missing_examples"],
              review_summary: {
                sense_count: 1,
                form_variant_count: 0,
                confusable_count: 0,
                provenance_sources: [],
                primary_definition: "good luck",
                primary_example: null,
              },
              compiled_payload: { entry_id: "phrase:break-a-leg", word: "break a leg" },
            }
          : {
              entry_id: "word:harbor",
              entry_type: "word",
              normalized_form: "harbor",
              display_text: "harbor",
              review_priority: "normal",
              warning_count: 0,
              warning_labels: [],
              review_summary: {
                sense_count: 1,
                form_variant_count: 1,
                confusable_count: 0,
                provenance_sources: ["snapshot"],
                primary_definition: "a sheltered body of water",
                primary_example: "The ship reached the harbor.",
              },
              compiled_payload: { entry_id: "word:harbor", word: "harbor" },
            };
      return {
        item: {
          ...base,
          review_status: payload.reviewStatus,
          decision_reason: payload.decisionReason,
          reviewed_at: "2026-03-21T02:00:00Z",
        },
        total_items: 3,
        pending_count: payload.reviewStatus === "pending" ? 2 : 1,
        approved_count: payload.reviewStatus === "approved" ? 2 : 1,
        rejected_count: payload.reviewStatus === "rejected" ? 1 : 0,
      };
    });
    mockMaterialize.mockResolvedValue({
      id: "job-1",
      created_by: "user-1",
      job_type: "jsonl_materialize",
      status: "running",
      target_key: "jsonl_materialize:/tmp/reviewed",
      request_payload: {
        artifact_path: "/tmp/words.enriched.jsonl",
        decisions_path: "/tmp/reviewed/review.decisions.jsonl",
        output_dir: "/tmp/reviewed",
      },
      result_payload: null,
      progress_total: 0,
      progress_completed: 0,
      progress_current_label: null,
      error_message: null,
      created_at: "2026-03-21T02:00:00Z",
      started_at: "2026-03-21T02:00:01Z",
      completed_at: null,
    });
    mockGetLexiconJob.mockResolvedValue({
      id: "job-1",
      created_by: "user-1",
      job_type: "jsonl_materialize",
      status: "completed",
      target_key: "jsonl_materialize:/tmp/reviewed",
      request_payload: {
        artifact_path: "/tmp/words.enriched.jsonl",
        decisions_path: "/tmp/reviewed/review.decisions.jsonl",
        output_dir: "/tmp/reviewed",
      },
      result_payload: {
        approved_count: 1,
        rejected_count: 1,
        regenerate_count: 1,
        approved_output_path: "/tmp/reviewed/approved.jsonl",
        rejected_output_path: "/tmp/reviewed/rejected.jsonl",
        regenerate_output_path: "/tmp/reviewed/regenerate.jsonl",
        decisions_output_path: "/tmp/reviewed/review.decisions.jsonl",
      },
      progress_total: 0,
      progress_completed: 0,
      progress_current_label: null,
      error_message: null,
      created_at: "2026-03-21T02:00:00Z",
      started_at: "2026-03-21T02:00:01Z",
      completed_at: "2026-03-21T02:00:02Z",
    });
    mockDownloadApproved.mockResolvedValue("{\"entry_id\":\"word:bank\"}\n");
    mockBulkUpdateItems.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 3,
      pending_count: 0,
      approved_count: 3,
      rejected_count: 0,
    });
  });

  it("renders the enrichment review submenu", async () => {
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-jsonl-review-page")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-enrichment-review-section-nav")).toHaveTextContent("Compiled Review");
    expect(screen.getByTestId("lexicon-enrichment-review-section-nav")).toHaveTextContent("JSONL Review");
  });

  it("loads rows, applies immediate decisions, advances to the next pending item, and materializes outputs", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/jsonl-review?artifactPath=%2Ftmp%2Fwords.enriched.jsonl&decisionsPath=%2Ftmp%2Freviewed%2Freview.decisions.jsonl&outputDir=%2Ftmp%2Freviewed&sourceReference=lexicon-20260321-wordfreq&autostart=1",
    );
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-jsonl-review-title")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent("Artifact: /tmp/words.enriched.jsonl"));
    expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent(
      "Source reference: lexicon-20260321-wordfreq",
    );
    expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent(
      "Output dir: /tmp/reviewed",
    );
    expect(screen.getByTestId("lexicon-jsonl-review-context")).toHaveTextContent(
      "Stage: Alternate review path",
    );
    expect(screen.getByText(/Approve keeps the compiled row eligible for reviewed\/approved\.jsonl, the reviewed file you should import into the final DB\./)).toBeInTheDocument();
    expect(screen.getByText(/Reject records the row in reviewed\/review\.decisions\.jsonl, writes the rejected overlay, and adds a regeneration request row\./)).toBeInTheDocument();
    expect(screen.getByText(/Reopen removes the final decision so the row stays pending until you decide again\./)).toBeInTheDocument();
    expect(screen.getByLabelText("Artifact path")).toHaveValue("/tmp/words.enriched.jsonl");
    expect(screen.getByLabelText("Decision ledger path")).toHaveValue("/tmp/reviewed/review.decisions.jsonl");
    expect(screen.getByLabelText("Output directory")).toHaveValue("/tmp/reviewed");
    expect(screen.getAllByLabelText("Output directory")).toHaveLength(1);

    await waitFor(() =>
      expect(mockGetSessionSummary).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        outputDir: "/tmp/reviewed",
      }),
    );
    await waitFor(() =>
      expect(mockBrowseItems).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        outputDir: "/tmp/reviewed",
        limit: 25,
        offset: 0,
        reviewStatus: "all",
        search: undefined,
      }),
    );
    await waitFor(() => expect(screen.getAllByText("break a leg").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("missing_source_provenance").length).toBeGreaterThan(0));
    expect(screen.getByText("Risk first")).toBeInTheDocument();
    expect(screen.getByText(/Shortcuts:/)).toBeInTheDocument();

    await user.click(screen.getByText("Risk first"));
    await user.keyboard("j");
    await waitFor(() => expect(screen.getAllByText("break a leg").length).toBeGreaterThan(0));

    mockBrowseItems.mockResolvedValueOnce({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 3,
      pending_count: 2,
      approved_count: 1,
      rejected_count: 0,
      filtered_total: 1,
      limit: 25,
      offset: 0,
      has_more: false,
      items: [
        {
          entry_id: "phrase:break-a-leg",
          entry_type: "phrase",
          normalized_form: "break a leg",
          display_text: "break a leg",
          review_priority: "warning",
          warning_count: 2,
          warning_labels: ["missing_source_provenance", "missing_examples"],
          review_summary: {
            sense_count: 1,
            form_variant_count: 0,
            confusable_count: 0,
            provenance_sources: [],
            primary_definition: "good luck",
            primary_example: null,
          },
          review_status: "pending",
          decision_reason: null,
          reviewed_at: null,
          compiled_payload: { entry_id: "phrase:break-a-leg", word: "break a leg" },
        },
      ],
    });
    await user.type(screen.getByPlaceholderText("Search entry id or display text"), "break");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() =>
      expect(mockBrowseItems).toHaveBeenLastCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        outputDir: "/tmp/reviewed",
        limit: 25,
        offset: 0,
        reviewStatus: "all",
        search: "break",
      }),
    );
    await waitFor(() => expect(screen.queryByText("bank")).not.toBeInTheDocument());

    await user.type(screen.getByTestId("jsonl-review-decision-reason"), "regen");
    await user.click(screen.getByTestId("jsonl-review-reject-button"));

    await waitFor(() =>
      expect(mockUpdateItem).toHaveBeenCalledWith("phrase:break-a-leg", {
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        reviewStatus: "rejected",
        decisionReason: "regen",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Download Approved Rows" }));
    await waitFor(() =>
      expect(mockDownloadApproved).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        outputDir: "/tmp/reviewed",
      }),
    );

    await user.click(screen.getByRole("button", { name: "Materialize Reviewed Outputs" }));
    await waitFor(() =>
      expect(mockMaterialize).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        outputDir: "/tmp/reviewed",
      }),
    );
    await waitFor(() => expect(mockGetLexiconJob).toHaveBeenCalledWith("job-1"));
  });

  it("paginates the JSONL review entry rail to keep the detail workspace focused", async () => {
    mockGetSessionSummary.mockResolvedValueOnce({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 12,
      pending_count: 12,
      approved_count: 0,
      rejected_count: 0,
    });
    mockBrowseItems
      .mockResolvedValueOnce({
        artifact_filename: "words.enriched.jsonl",
        artifact_path: "/tmp/words.enriched.jsonl",
        decisions_path: "/tmp/reviewed/review.decisions.jsonl",
        output_dir: "/tmp/reviewed",
        total_items: 12,
        pending_count: 12,
        approved_count: 0,
        rejected_count: 0,
        filtered_total: 12,
        limit: 25,
        offset: 0,
        has_more: false,
        items: Array.from({ length: 12 }, (_, index) => ({
          entry_id: `word:item-${index + 1}`,
          entry_type: "word",
          normalized_form: `item-${index + 1}`,
          display_text: `item-${index + 1}`,
          entity_category: "general",
          language: "en",
          frequency_rank: 100 + index,
          cefr_level: "B1",
          review_priority: "normal",
          warning_count: 0,
          warning_labels: [],
          review_summary: {
            sense_count: 1,
            form_variant_count: 0,
            confusable_count: 0,
            provenance_sources: ["snapshot"],
            primary_definition: `definition ${index + 1}`,
            primary_example: `example ${index + 1}`,
          },
          review_status: "pending",
          decision_reason: null,
          reviewed_by: null,
          reviewed_at: null,
          compiled_payload: { entry_id: `word:item-${index + 1}`, word: `item-${index + 1}` },
          compiled_payload_sha256: `${index + 1}`.repeat(64),
        })),
      });

    const user = userEvent.setup();
    window.history.pushState({}, "", "/lexicon/jsonl-review?artifactPath=%2Ftmp%2Fwords.enriched.jsonl&autostart=1");
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByTestId("jsonl-review-items-list")).toBeInTheDocument());
    expect(within(screen.getByTestId("jsonl-review-items-list")).getByText("item-1")).toBeInTheDocument();
    expect(within(screen.getByTestId("jsonl-review-items-list")).getByText("item-12")).toBeInTheDocument();
    expect(screen.getByText("12 matches · page 1")).toBeInTheDocument();
  });

  it("confirms bulk approve all and refreshes the session counts", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/jsonl-review?artifactPath=%2Ftmp%2Fwords.enriched.jsonl&decisionsPath=%2Ftmp%2Freviewed%2Freview.decisions.jsonl&outputDir=%2Ftmp%2Freviewed&sourceReference=lexicon-20260321-wordfreq&autostart=1",
    );
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByText("break a leg")).toBeInTheDocument());
    await user.clear(screen.getByTestId("jsonl-review-decision-reason"));
    await user.type(screen.getByTestId("jsonl-review-decision-reason"), "bulk ready");
    await user.click(screen.getByTestId("jsonl-review-approve-all-button"));

    expect(mockBulkUpdateItems).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("jsonl-review-confirm-bulk-approved-button"));

    await waitFor(() =>
      expect(mockBulkUpdateItems).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        reviewStatus: "approved",
        decisionReason: "bulk ready",
      }),
    );
  });

  it("renders structured phrase details from the compiled payload", async () => {
    mockGetSessionSummary.mockResolvedValueOnce({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 1,
      pending_count: 1,
      approved_count: 0,
      rejected_count: 0,
    });
    mockBrowseItems.mockResolvedValueOnce({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 1,
      pending_count: 1,
      approved_count: 0,
      rejected_count: 0,
      filtered_total: 1,
      limit: 25,
      offset: 0,
      has_more: false,
      items: [
        {
          entry_id: "phrase:break-a-leg",
          entry_type: "phrase",
          normalized_form: "break a leg",
          display_text: "Break a leg",
          review_priority: "warning",
          warning_count: 1,
          warning_labels: ["missing_source_provenance"],
          review_summary: {
            sense_count: 1,
            form_variant_count: 0,
            confusable_count: 0,
            provenance_sources: [],
            primary_definition: "good luck",
            primary_example: "Break a leg tonight.",
          },
          review_status: "pending",
          decision_reason: null,
          reviewed_at: null,
          compiled_payload: {
            entry_id: "phrase:break-a-leg",
            phrase_kind: "idiom",
            senses: [
              {
                definition: "good luck",
                examples: ["Break a leg tonight."],
                translations: {
                  es: {
                    definition: "buena suerte",
                  },
                },
              },
            ],
          },
        },
      ],
    });
    window.history.pushState(
      {},
      "",
      "/lexicon/jsonl-review?artifactPath=%2Ftmp%2Fwords.enriched.jsonl&decisionsPath=%2Ftmp%2Freviewed%2Freview.decisions.jsonl&outputDir=%2Ftmp%2Freviewed",
    );
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByTestId("jsonl-review-phrase-details")).toBeInTheDocument());
    const phraseDetails = screen.getByTestId("jsonl-review-phrase-details");
    expect(within(phraseDetails).getByText("Phrase details")).toBeInTheDocument();
    expect(within(phraseDetails).getByText("idiom")).toBeInTheDocument();
    expect(within(phraseDetails).getByText("good luck")).toBeInTheDocument();
    expect(within(phraseDetails).getByText("Break a leg tonight.")).toBeInTheDocument();
    expect(within(phraseDetails).getByText("buena suerte")).toBeInTheDocument();
  });
});
