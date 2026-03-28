import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconCompiledReviewPage from "@/app/lexicon/compiled-review/page";
import {
  deleteLexiconCompiledReviewBatch,
  downloadCompiledReviewDecisionsExport,
  downloadApprovedCompiledReviewExport,
  importLexiconCompiledReviewBatch,
  importLexiconCompiledReviewBatchByPath,
  listLexiconCompiledReviewBatches,
  listLexiconCompiledReviewItems,
  updateLexiconCompiledReviewItem,
} from "@/lib/lexicon-compiled-reviews-client";
import {
  createCompiledMaterializeLexiconJob,
  createCompiledReviewBulkUpdateLexiconJob,
  getLexiconJob,
} from "@/lib/lexicon-jobs-client";

jest.mock("@/lib/lexicon-compiled-reviews-client", () => ({
  deleteLexiconCompiledReviewBatch: jest.fn(),
  downloadCompiledReviewDecisionsExport: jest.fn(),
  downloadApprovedCompiledReviewExport: jest.fn(),
  downloadRegenerateCompiledReviewExport: jest.fn(),
  downloadRejectedCompiledReviewExport: jest.fn(),
  getLexiconCompiledReviewBatch: jest.fn(),
  importLexiconCompiledReviewBatch: jest.fn(),
  importLexiconCompiledReviewBatchByPath: jest.fn(),
  listLexiconCompiledReviewBatches: jest.fn(),
  listLexiconCompiledReviewItems: jest.fn(),
  updateLexiconCompiledReviewItem: jest.fn(),
}));

jest.mock("@/lib/lexicon-jobs-client", () => ({
  createCompiledMaterializeLexiconJob: jest.fn(),
  createCompiledReviewBulkUpdateLexiconJob: jest.fn(),
  getLexiconJob: jest.fn(),
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
  const mockDeleteBatch = deleteLexiconCompiledReviewBatch as jest.Mock;
  const mockDownloadDecisions = downloadCompiledReviewDecisionsExport as jest.Mock;
  const mockDownloadApproved = downloadApprovedCompiledReviewExport as jest.Mock;
  const mockImportBatch = importLexiconCompiledReviewBatch as jest.Mock;
  const mockImportBatchByPath = importLexiconCompiledReviewBatchByPath as jest.Mock;
  const mockMaterializeOutputs = createCompiledMaterializeLexiconJob as jest.Mock;
  const mockCreateBulkJob = createCompiledReviewBulkUpdateLexiconJob as jest.Mock;
  const mockGetLexiconJob = getLexiconJob as jest.Mock;

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
        artifact_row_count: 2,
        compiled_schema_version: "1.1.0",
        snapshot_id: "snapshot-001",
        source_type: "lexicon_compiled_export",
        source_reference: "snapshot-001",
        status: "pending_review",
        total_items: 2,
        pending_count: 2,
        approved_count: 0,
        rejected_count: 0,
        created_by: "user-1",
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
        completed_at: null,
      },
    ]);
    mockListItems.mockResolvedValue({
      items: [
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
        {
          id: "item-2",
          batch_id: "batch-1",
          entry_id: "word:harbor",
          entry_type: "word",
          normalized_form: "harbor",
          display_text: "harbor",
          entity_category: "general",
          language: "en",
          frequency_rank: 120,
          cefr_level: "B1",
          review_status: "pending",
          review_priority: 90,
          validator_status: "pass",
          validator_issues: [],
          qc_status: "pass",
          qc_score: 0.9,
          qc_issues: [],
          regen_requested: false,
          import_eligible: false,
          decision_reason: null,
          reviewed_by: null,
          reviewed_at: null,
          compiled_payload: { entry_id: "word:harbor", word: "harbor" },
          compiled_payload_sha256: "c".repeat(64),
          created_at: "2026-03-21T00:00:00Z",
          updated_at: "2026-03-21T00:00:00Z",
        },
      ],
      total: 2,
      limit: 50,
      offset: 0,
      has_more: false,
    });
    mockUpdateItem.mockImplementation(async (itemId: string, payload: { review_status: string; decision_reason: string | null }) => {
      const base =
        itemId === "item-1"
          ? {
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
              validator_issues: [{ code: "missing_usage_note" }],
              qc_status: "fail",
              qc_score: 0.4,
              qc_issues: [{ code: "example_too_literal" }],
              compiled_payload: { entry_id: "word:bank", word: "bank" },
              compiled_payload_sha256: "b".repeat(64),
              created_at: "2026-03-21T00:00:00Z",
              updated_at: "2026-03-21T00:00:00Z",
            }
          : {
              id: "item-2",
              batch_id: "batch-1",
              entry_id: "word:harbor",
              entry_type: "word",
              normalized_form: "harbor",
              display_text: "harbor",
              entity_category: "general",
              language: "en",
              frequency_rank: 120,
              cefr_level: "B1",
              review_priority: 90,
              validator_status: "pass",
              validator_issues: [],
              qc_status: "pass",
              qc_score: 0.9,
              qc_issues: [],
              compiled_payload: { entry_id: "word:harbor", word: "harbor" },
              compiled_payload_sha256: "c".repeat(64),
              created_at: "2026-03-21T00:00:00Z",
              updated_at: "2026-03-21T00:00:00Z",
            };
      return {
        ...base,
        review_status: payload.review_status,
        import_eligible: payload.review_status === "approved",
        regen_requested: payload.review_status === "rejected",
        decision_reason: payload.decision_reason,
        reviewed_by: "user-1",
        reviewed_at: "2026-03-21T01:00:00Z",
      };
    });
    mockCreateBulkJob.mockResolvedValue({
      id: "job-bulk-1",
      created_by: "user-1",
      job_type: "compiled_review_bulk_update",
      status: "queued",
      target_key: "compiled_review_bulk_update:batch-1:approved:all_pending",
      request_payload: {
        batch_id: "batch-1",
        review_status: "approved",
        decision_reason: "bulk ready",
        scope: "all_pending",
      },
      result_payload: null,
      progress_total: 2,
      progress_completed: 0,
      progress_current_label: null,
      error_message: null,
      created_at: "2026-03-21T02:00:00Z",
      started_at: null,
      completed_at: null,
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
    mockImportBatchByPath.mockResolvedValue({
      id: "batch-3",
      artifact_family: "compiled_words",
      artifact_filename: "words.enriched.jsonl",
      artifact_sha256: "d".repeat(64),
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
    mockMaterializeOutputs.mockResolvedValue({
      id: "job-1",
      created_by: "user-1",
      job_type: "compiled_materialize",
      status: "running",
      target_key: "compiled_materialize:batch-1:/app/data/lexicon/snapshots/words-100-20260312/reviewed",
      request_payload: {
        batch_id: "batch-1",
        output_dir: "/app/data/lexicon/snapshots/words-100-20260312/reviewed",
      },
      result_payload: null,
      progress_total: 0,
      progress_completed: 0,
      progress_current_label: null,
      error_message: null,
      created_at: "2026-03-21T00:00:00Z",
      started_at: "2026-03-21T00:00:01Z",
      completed_at: null,
    });
    mockGetLexiconJob.mockResolvedValue({
      id: "job-1",
      created_by: "user-1",
      job_type: "compiled_materialize",
      status: "completed",
      target_key: "compiled_materialize:batch-1:/app/data/lexicon/snapshots/words-100-20260312/reviewed",
      request_payload: {
        batch_id: "batch-1",
        output_dir: "/app/data/lexicon/snapshots/words-100-20260312/reviewed",
      },
      result_payload: {
        approved_output_path: "/app/data/lexicon/snapshots/words-100-20260312/reviewed/approved.jsonl",
        decisions_output_path: "/app/data/lexicon/snapshots/words-100-20260312/reviewed/review.decisions.jsonl",
        rejected_output_path: "/app/data/lexicon/snapshots/words-100-20260312/reviewed/rejected.jsonl",
        regenerate_output_path: "/app/data/lexicon/snapshots/words-100-20260312/reviewed/regenerate.jsonl",
        approved_count: 1,
        rejected_count: 0,
        regenerate_count: 0,
        decision_count: 1,
      },
      progress_total: 0,
      progress_completed: 0,
      progress_current_label: null,
      error_message: null,
      created_at: "2026-03-21T00:00:00Z",
      started_at: "2026-03-21T00:00:01Z",
      completed_at: "2026-03-21T00:00:02Z",
    });
    mockGetLexiconJob.mockResolvedValueOnce({
      id: "job-bulk-1",
      created_by: "user-1",
      job_type: "compiled_review_bulk_update",
      status: "running",
      target_key: "compiled_review_bulk_update:batch-1:approved:all_pending",
      request_payload: {
        batch_id: "batch-1",
        review_status: "approved",
        decision_reason: "bulk ready",
        scope: "all_pending",
      },
      result_payload: null,
      progress_total: 2,
      progress_completed: 1,
      progress_current_label: "bank",
      error_message: null,
      created_at: "2026-03-21T02:00:00Z",
      started_at: "2026-03-21T02:00:01Z",
      completed_at: null,
    });
    mockGetLexiconJob.mockResolvedValueOnce({
      id: "job-bulk-1",
      created_by: "user-1",
      job_type: "compiled_review_bulk_update",
      status: "completed",
      target_key: "compiled_review_bulk_update:batch-1:approved:all_pending",
      request_payload: {
        batch_id: "batch-1",
        review_status: "approved",
        decision_reason: "bulk ready",
        scope: "all_pending",
      },
      result_payload: {
        batch_id: "batch-1",
        processed_count: 2,
        approved_count: 2,
        rejected_count: 0,
        pending_count: 0,
        failed_count: 0,
        scope: "all_pending",
        review_status: "approved",
      },
      progress_total: 2,
      progress_completed: 2,
      progress_current_label: "harbor",
      error_message: null,
      created_at: "2026-03-21T02:00:00Z",
      started_at: "2026-03-21T02:00:01Z",
      completed_at: "2026-03-21T02:00:03Z",
    });
    mockDeleteBatch.mockResolvedValue(undefined);
  });

  it("renders batches, applies immediate decisions, advances to the next pending row, and downloads approved export", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/compiled-review?snapshot=words-100-20260312&sourceReference=lexicon-20260312-wordnet-wordfreq&artifactPath=%2Fdata%2Flexicon%2Fsnapshots%2Fwords-100-20260312%2Fwords.enriched.jsonl&autostart=1",
    );
    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-compiled-review-title")).toBeInTheDocument());
    await waitFor(() => expect(mockImportBatchByPath).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("compiled-review-item-title")).toHaveTextContent("bank"));

    await user.type(screen.getByTestId("compiled-review-decision-reason"), "ready");
    await user.click(screen.getByTestId("compiled-review-approve-button"));

    await waitFor(() =>
      expect(mockUpdateItem).toHaveBeenCalledWith("item-1", { review_status: "approved", decision_reason: "ready" }),
    );
    await waitFor(() => expect(screen.getByTestId("compiled-review-item-title")).toHaveTextContent("harbor"));

    await user.click(screen.getByRole("button", { name: "Download Approved Rows" }));
    await waitFor(() => expect(mockDownloadApproved).toHaveBeenCalledWith("batch-1"));
    await user.click(screen.getByRole("button", { name: "Download Decision Ledger" }));
    await waitFor(() => expect(mockDownloadDecisions).toHaveBeenCalledWith("batch-1"));
    await user.click(screen.getByRole("button", { name: "Materialize Reviewed Outputs" }));
    await waitFor(() =>
      expect(mockMaterializeOutputs).toHaveBeenCalledWith({
        batchId: "batch-1",
        outputDir: "/app/data/lexicon/snapshots/words-100-20260312/reviewed",
      }),
    );
    await waitFor(() => expect(mockGetLexiconJob).toHaveBeenCalledWith("job-1"));
  });

  it("deletes a compiled review batch after confirmation", async () => {
    const user = userEvent.setup();
    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("compiled-review-batches-list")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Delete Batch" }));
    await user.click(screen.getByRole("button", { name: "Confirm Delete Batch" }));

    await waitFor(() => expect(mockDeleteBatch).toHaveBeenCalledWith("batch-1"));
  });

  it("confirms bulk approve all and updates batch counts", async () => {
    const user = userEvent.setup();
    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("compiled-review-item-title")).toHaveTextContent("bank"));
    await user.type(screen.getByTestId("compiled-review-decision-reason"), "bulk ready");
    await user.click(screen.getByTestId("compiled-review-approve-all-button"));

    expect(mockCreateBulkJob).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("compiled-review-confirm-bulk-approved-button"));

    await waitFor(() =>
      expect(mockCreateBulkJob).toHaveBeenCalledWith({
        batchId: "batch-1",
        reviewStatus: "approved",
        decisionReason: "bulk ready",
        scope: "all_pending",
      }),
    );
    await waitFor(() => expect(screen.getByTestId("compiled-review-bulk-job-progress")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Completed bulk approved job for 2 rows\./i)).toBeInTheDocument());
  });

  it("loads the next server window of compiled review items", async () => {
    const user = userEvent.setup();
    mockListItems
      .mockResolvedValueOnce({
        items: [
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
            validator_issues: [],
            qc_status: "pass",
            qc_score: 0.8,
            qc_issues: [],
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
        ],
        total: 60,
        limit: 50,
        offset: 0,
        has_more: true,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: "item-51",
            batch_id: "batch-1",
            entry_id: "word:zebra",
            entry_type: "word",
            normalized_form: "zebra",
            display_text: "zebra",
            entity_category: "general",
            language: "en",
            frequency_rank: 600,
            cefr_level: "B1",
            review_status: "pending",
            review_priority: 10,
            validator_status: "pass",
            validator_issues: [],
            qc_status: "pass",
            qc_score: 0.95,
            qc_issues: [],
            regen_requested: false,
            import_eligible: false,
            decision_reason: null,
            reviewed_by: null,
            reviewed_at: null,
            compiled_payload: { entry_id: "word:zebra", word: "zebra" },
            compiled_payload_sha256: "z".repeat(64),
            created_at: "2026-03-21T00:00:00Z",
            updated_at: "2026-03-21T00:00:00Z",
          },
        ],
        total: 60,
        limit: 50,
        offset: 50,
        has_more: false,
      });

    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("compiled-review-item-title")).toHaveTextContent("bank"));
    await user.click(screen.getByRole("button", { name: "Next 50" }));

    await waitFor(() =>
      expect(mockListItems).toHaveBeenLastCalledWith("batch-1", {
        limit: 50,
        offset: 50,
        reviewStatus: undefined,
        search: undefined,
      }),
    );
    await waitFor(() => expect(screen.getByTestId("compiled-review-item-title")).toHaveTextContent("zebra"));
    expect(screen.getByText("Showing 51-51 of 60")).toBeInTheDocument();
  });

  it("renders structured phrase details from compiled phrase rows", async () => {
    mockListItems.mockResolvedValueOnce({
      items: [
      {
        id: "item-phrase-1",
        batch_id: "batch-1",
        entry_id: "phrase:break-a-leg",
        entry_type: "phrase",
        normalized_form: "break a leg",
        display_text: "Break a leg",
        entity_category: "general",
        language: "en",
        frequency_rank: 250,
        cefr_level: "B1",
        review_status: "pending",
        review_priority: 95,
        validator_status: "pass",
        validator_issues: [],
        qc_status: "pass",
        qc_score: 0.91,
        qc_issues: [],
        regen_requested: false,
        import_eligible: false,
        decision_reason: null,
        reviewed_by: null,
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
        compiled_payload_sha256: "d".repeat(64),
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
      },
      ],
      total: 1,
      limit: 50,
      offset: 0,
      has_more: false,
    });
    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("compiled-review-phrase-details")).toBeInTheDocument());
    expect(screen.getByText("Phrase details")).toBeInTheDocument();
    expect(screen.getAllByText("idiom").length).toBeGreaterThan(0);
    expect(screen.getAllByText("good luck").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Break a leg tonight.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("buena suerte").length).toBeGreaterThan(0);
  });

  it("paginates the entry rail and exposes horizontal batch browsing controls", async () => {
    mockListBatches.mockResolvedValueOnce(
      Array.from({ length: 4 }, (_, index) => ({
        id: `batch-${index + 1}`,
        artifact_family: "compiled_words",
        artifact_filename: `words-${index + 1}.enriched.jsonl`,
        artifact_sha256: `${index + 1}`.repeat(64),
        artifact_row_count: 12,
        compiled_schema_version: "1.1.0",
        snapshot_id: `snapshot-00${index + 1}`,
        source_type: "lexicon_compiled_export",
        source_reference: `snapshot-00${index + 1}`,
        status: "pending_review",
        total_items: 12,
        pending_count: 12,
        approved_count: 0,
        rejected_count: 0,
        created_by: "user-1",
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
        completed_at: null,
      })),
    );
    mockListItems.mockResolvedValueOnce({
      items: Array.from({ length: 12 }, (_, index) => ({
        id: `item-${index + 1}`,
        batch_id: "batch-1",
        entry_id: `word:item-${index + 1}`,
        entry_type: "word",
        normalized_form: `item-${index + 1}`,
        display_text: `item-${index + 1}`,
        entity_category: "general",
        language: "en",
        frequency_rank: 100 + index,
        cefr_level: "B1",
        review_status: "pending",
        review_priority: 100 - index,
        validator_status: "pass",
        validator_issues: [],
        qc_status: "pass",
        qc_score: 0.9,
        qc_issues: [],
        regen_requested: false,
        import_eligible: false,
        decision_reason: null,
        reviewed_by: null,
        reviewed_at: null,
        compiled_payload: { entry_id: `word:item-${index + 1}`, word: `item-${index + 1}` },
        compiled_payload_sha256: `${index + 1}`.repeat(64),
        created_at: "2026-03-21T00:00:00Z",
        updated_at: "2026-03-21T00:00:00Z",
      })),
      total: 12,
      limit: 50,
      offset: 0,
      has_more: false,
    });

    const user = userEvent.setup();
    window.history.pushState({}, "", "/lexicon/compiled-review");
    render(<LexiconCompiledReviewPage />);

    await waitFor(() => expect(screen.getByTestId("compiled-review-batch-rail")).toBeInTheDocument());
    expect(within(screen.getByTestId("compiled-review-batch-rail")).getByText("words-1.enriched.jsonl")).toBeInTheDocument();
    expect(within(screen.getByTestId("compiled-review-batch-rail")).queryByText("words-4.enriched.jsonl")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("compiled-review-batch-rail-next"));
    await waitFor(() =>
      expect(within(screen.getByTestId("compiled-review-batch-rail")).getByText("words-4.enriched.jsonl")).toBeInTheDocument(),
    );

    await waitFor(() => expect(within(screen.getByTestId("compiled-review-items-list")).getByText("item-1")).toBeInTheDocument());
    expect(within(screen.getByTestId("compiled-review-items-list")).getByText("item-5")).toBeInTheDocument();
    expect(within(screen.getByTestId("compiled-review-items-list")).queryByText("item-6")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("compiled-review-items-list-next-page"));
    expect(within(screen.getByTestId("compiled-review-items-list")).getByText("item-6")).toBeInTheDocument();
    expect(within(screen.getByTestId("compiled-review-items-list")).getByText("item-10")).toBeInTheDocument();
  });
});
