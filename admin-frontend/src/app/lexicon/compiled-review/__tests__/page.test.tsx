import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconCompiledReviewPage from "@/app/lexicon/compiled-review/page";
import {
  downloadCompiledReviewDecisionsExport,
  downloadApprovedCompiledReviewExport,
  importLexiconCompiledReviewBatch,
  listLexiconCompiledReviewBatches,
  listLexiconCompiledReviewItems,
  updateLexiconCompiledReviewItem,
} from "@/lib/lexicon-compiled-reviews-client";

jest.mock("@/lib/lexicon-compiled-reviews-client", () => ({
  downloadCompiledReviewDecisionsExport: jest.fn(),
  downloadApprovedCompiledReviewExport: jest.fn(),
  downloadRegenerateCompiledReviewExport: jest.fn(),
  downloadRejectedCompiledReviewExport: jest.fn(),
  getLexiconCompiledReviewBatch: jest.fn(),
  importLexiconCompiledReviewBatch: jest.fn(),
  listLexiconCompiledReviewBatches: jest.fn(),
  listLexiconCompiledReviewItems: jest.fn(),
  updateLexiconCompiledReviewItem: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconCompiledReviewPage", () => {
  const mockListBatches = listLexiconCompiledReviewBatches as jest.Mock;
  const mockListItems = listLexiconCompiledReviewItems as jest.Mock;
  const mockUpdateItem = updateLexiconCompiledReviewItem as jest.Mock;
  const mockDownloadDecisions = downloadCompiledReviewDecisionsExport as jest.Mock;
  const mockDownloadApproved = downloadApprovedCompiledReviewExport as jest.Mock;
  const mockImportBatch = importLexiconCompiledReviewBatch as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    URL.createObjectURL = jest.fn(() => "blob:test");
    URL.revokeObjectURL = jest.fn();
    HTMLAnchorElement.prototype.click = jest.fn();
    mockListBatches.mockResolvedValue([
      {
        id: "batch-1",
        artifact_family: "compiled_words",
        artifact_filename: "words.enriched.jsonl",
        artifact_sha256: "a".repeat(64),
        artifact_row_count: 1,
        compiled_schema_version: "1.1.0",
        snapshot_id: "snapshot-001",
        source_type: "lexicon_compiled_export",
        source_reference: "snapshot-001",
        status: "pending_review",
        total_items: 1,
        pending_count: 1,
        approved_count: 0,
        rejected_count: 0,
        created_by: "user-1",
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
        completed_at: null,
      },
    ]);
    mockListItems.mockResolvedValue([
      {
        id: "item-1",
        batch_id: "batch-1",
        entry_id: "word:bank",
        entry_type: "word",
        normalized_form: "bank",
        display_text: "bank",
        entity_category: "general",
        language: "en",
        frequency_rank: 100,
        cefr_level: "B1",
        review_status: "pending",
        review_priority: 100,
        validator_status: "warn",
        validator_issues: [{ code: "missing_usage_note" }],
        qc_status: "fail",
        qc_score: 0.4,
        qc_issues: [{ code: "example_too_literal" }],
        regen_requested: false,
        import_eligible: false,
        decision_reason: null,
        reviewed_by: null,
        reviewed_at: null,
        compiled_payload: { entry_id: "word:bank", word: "bank" },
        compiled_payload_sha256: "b".repeat(64),
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
      },
    ]);
    mockUpdateItem.mockResolvedValue({
      ...(mockListItems.mock.results[0]?.value?.[0] ?? {
        id: "item-1",
        batch_id: "batch-1",
        entry_id: "word:bank",
        entry_type: "word",
        normalized_form: "bank",
        display_text: "bank",
        entity_category: "general",
        language: "en",
        frequency_rank: 100,
        cefr_level: "B1",
        review_priority: 100,
        validator_status: "warn",
        validator_issues: [],
        qc_status: "fail",
        qc_score: 0.4,
        qc_issues: [],
        compiled_payload: { entry_id: "word:bank", word: "bank" },
        compiled_payload_sha256: "b".repeat(64),
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
      }),
      review_status: "approved",
      import_eligible: true,
      regen_requested: false,
      decision_reason: "ready",
      reviewed_by: "user-1",
      reviewed_at: "2026-03-21T01:00:00Z",
    });
    mockDownloadApproved.mockResolvedValue("{\"entry_id\":\"word:bank\"}\n");
    mockDownloadDecisions.mockResolvedValue("{\"entry_id\":\"word:bank\",\"decision\":\"approved\"}\n");
    mockImportBatch.mockResolvedValue({
      id: "batch-2",
      artifact_family: "compiled_words",
      artifact_filename: "imported.jsonl",
      artifact_sha256: "c".repeat(64),
      artifact_row_count: 1,
      compiled_schema_version: "1.1.0",
      snapshot_id: "snapshot-002",
      source_type: "lexicon_compiled_export",
      source_reference: "snapshot-002",
      status: "pending_review",
      total_items: 1,
      pending_count: 1,
      approved_count: 0,
      rejected_count: 0,
      created_by: "user-1",
      created_at: "2026-03-21T00:00:00Z",
      updated_at: "2026-03-21T00:00:00Z",
      completed_at: null,
    });
  });

  it("renders batches, allows approve, and downloads approved export", async () => {
    const user = userEvent.setup();
    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-compiled-review-title")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("words.enriched.jsonl").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByTestId("compiled-review-item-title")).toHaveTextContent("bank"));

    await user.type(screen.getByTestId("compiled-review-decision-reason"), "ready");
    await user.click(screen.getByTestId("compiled-review-approve-button"));

    await waitFor(() =>
      expect(mockUpdateItem).toHaveBeenCalledWith("item-1", { review_status: "approved", decision_reason: "ready" }),
    );

    await user.click(screen.getByTestId("compiled-review-export-approved"));
    await waitFor(() => expect(mockDownloadApproved).toHaveBeenCalledWith("batch-1"));
    await user.click(screen.getByRole("button", { name: "Export Decisions" }));
    await waitFor(() => expect(mockDownloadDecisions).toHaveBeenCalledWith("batch-1"));
  });
});
