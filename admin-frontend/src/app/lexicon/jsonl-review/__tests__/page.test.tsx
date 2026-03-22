import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconJsonlReviewPage from "@/app/lexicon/jsonl-review/page";
import {
  bulkUpdateLexiconJsonlReviewItems,
  downloadApprovedLexiconJsonlReviewOutput,
  downloadDecisionLexiconJsonlReviewOutput,
  downloadRegenerateLexiconJsonlReviewOutput,
  downloadRejectedLexiconJsonlReviewOutput,
  loadLexiconJsonlReviewSession,
  materializeLexiconJsonlReviewOutputs,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";

jest.mock("@/lib/lexicon-jsonl-reviews-client", () => ({
  bulkUpdateLexiconJsonlReviewItems: jest.fn(),
  downloadApprovedLexiconJsonlReviewOutput: jest.fn(),
  downloadDecisionLexiconJsonlReviewOutput: jest.fn(),
  downloadRegenerateLexiconJsonlReviewOutput: jest.fn(),
  downloadRejectedLexiconJsonlReviewOutput: jest.fn(),
  loadLexiconJsonlReviewSession: jest.fn(),
  materializeLexiconJsonlReviewOutputs: jest.fn(),
  updateLexiconJsonlReviewItem: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconJsonlReviewPage", () => {
  const mockLoadSession = loadLexiconJsonlReviewSession as jest.Mock;
  const mockUpdateItem = updateLexiconJsonlReviewItem as jest.Mock;
  const mockBulkUpdateItems = bulkUpdateLexiconJsonlReviewItems as jest.Mock;
  const mockMaterialize = materializeLexiconJsonlReviewOutputs as jest.Mock;
  const mockDownloadApproved = downloadApprovedLexiconJsonlReviewOutput as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    URL.createObjectURL = jest.fn(() => "blob:test");
    URL.revokeObjectURL = jest.fn();
    HTMLAnchorElement.prototype.click = jest.fn();
    mockLoadSession.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      artifact_path: "/tmp/words.enriched.jsonl",
      decisions_path: "/tmp/reviewed/review.decisions.jsonl",
      output_dir: "/tmp/reviewed",
      total_items: 3,
      pending_count: 2,
      approved_count: 1,
      rejected_count: 0,
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
    mockUpdateItem.mockResolvedValue({
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
      review_status: "rejected",
      decision_reason: "regen",
      reviewed_at: "2026-03-21T02:00:00Z",
      compiled_payload: { entry_id: "phrase:break-a-leg", word: "break a leg" },
    });
    mockMaterialize.mockResolvedValue({
      approved_count: 1,
      rejected_count: 1,
      regenerate_count: 1,
      approved_output_path: "/tmp/reviewed/approved.jsonl",
      rejected_output_path: "/tmp/reviewed/rejected.jsonl",
      regenerate_output_path: "/tmp/reviewed/regenerate.jsonl",
      decisions_output_path: "/tmp/reviewed/review.decisions.jsonl",
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
          decision_reason: "bulk ready",
          reviewed_at: "2026-03-21T02:00:00Z",
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
          review_status: "approved",
          decision_reason: "bulk ready",
          reviewed_at: "2026-03-21T02:00:00Z",
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
          review_status: "approved",
          decision_reason: "bulk ready",
          reviewed_at: "2026-03-21T02:00:00Z",
          compiled_payload: { entry_id: "word:harbor", word: "harbor" },
        },
      ],
    });
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

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() =>
      expect(mockLoadSession).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        outputDir: "/tmp/reviewed",
      }),
    );
    await waitFor(() => expect(screen.getAllByText("break a leg").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("missing_source_provenance").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText("good luck")).toBeInTheDocument());
    expect(screen.getByText("Risk first")).toBeInTheDocument();
    expect(screen.getByText(/Shortcuts:/)).toBeInTheDocument();

    await user.click(screen.getByText("Risk first"));
    await user.keyboard("j");
    await waitFor(() => expect(screen.getByText("break a leg")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("Search entry id or display text"), "break");
    expect(screen.getAllByText("break a leg").length).toBeGreaterThan(0);
    expect(screen.queryByText("bank")).not.toBeInTheDocument();

    await user.click(screen.getAllByText("break a leg")[0]);
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
    await user.clear(screen.getByPlaceholderText("Search entry id or display text"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "harbor" })).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("jsonl-review-approve-button"));
    await waitFor(() =>
      expect(mockUpdateItem).toHaveBeenCalledWith("word:harbor", {
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        reviewStatus: "approved",
        decisionReason: null,
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
    await waitFor(() => expect(screen.getByText("approved.jsonl")).toBeInTheDocument());
    expect(screen.getByText(/approved\.jsonl is the reviewed file for Import DB\./)).toBeInTheDocument();
  });

  it("confirms bulk approve all and refreshes the summary counts", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/jsonl-review?artifactPath=%2Ftmp%2Fwords.enriched.jsonl&decisionsPath=%2Ftmp%2Freviewed%2Freview.decisions.jsonl&outputDir=%2Ftmp%2Freviewed&sourceReference=lexicon-20260321-wordfreq&autostart=1",
    );
    render(<LexiconJsonlReviewPage />);

    await waitFor(() => expect(screen.getByText("Risk first")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("heading", { name: "break a leg" })).toBeInTheDocument());
    await user.type(screen.getByTestId("jsonl-review-decision-reason"), "bulk ready");
    await user.click(screen.getByTestId("jsonl-review-approve-all-button"));
    expect(mockBulkUpdateItems).not.toHaveBeenCalled();
    expect(screen.getByTestId("jsonl-review-confirm-bulk-approved-button")).toBeInTheDocument();

    await user.click(screen.getByTestId("jsonl-review-confirm-bulk-approved-button"));

    await waitFor(() =>
      expect(mockBulkUpdateItems).toHaveBeenCalledWith({
        artifactPath: "/tmp/words.enriched.jsonl",
        decisionsPath: "/tmp/reviewed/review.decisions.jsonl",
        reviewStatus: "approved",
        decisionReason: "bulk ready",
      }),
    );
    await waitFor(() => expect(screen.getAllByText("approved").length).toBeGreaterThan(0));
  });
});
