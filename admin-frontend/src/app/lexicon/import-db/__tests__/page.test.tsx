import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconImportDbPage from "@/app/lexicon/import-db/page";

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

jest.mock("@/lib/lexicon-imports-client", () => ({
  dryRunLexiconImport: jest.fn(),
}));

jest.mock("@/lib/lexicon-jobs-client", () => ({
  createImportDbLexiconJob: jest.fn(),
  getLexiconJob: jest.fn(),
  listLexiconJobs: jest.fn(),
}));

describe("LexiconImportDbPage", () => {
  const { dryRunLexiconImport } = require("@/lib/lexicon-imports-client");
  const { createImportDbLexiconJob, getLexiconJob, listLexiconJobs } = require("@/lib/lexicon-jobs-client");

  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    dryRunLexiconImport.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      import_summary: { dry_run: 1, failed_rows: 0 },
      error_samples: [],
    });
    getLexiconJob.mockResolvedValue({
      id: "job-1",
      created_by: "user-1",
      job_type: "import_db",
      status: "completed",
      target_key: "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      request_payload: {
        input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        source_type: "lexicon_snapshot",
        source_reference: "lexicon-20260321-wordfreq",
        language: "en",
        conflict_mode: "fail",
        error_mode: "continue",
        row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      },
      result_payload: { created_words: 1 },
      progress_summary: {
        phase: "completed",
        total: 1,
        validated: 1,
        imported: 1,
        skipped: 0,
        failed: 0,
        to_validate: 0,
        to_import: 0,
      },
      progress_total: 1,
      progress_completed: 1,
      progress_current_label: "bank",
      error_message: null,
      created_at: "2026-03-23T00:00:00Z",
      started_at: "2026-03-23T00:00:01Z",
      completed_at: "2026-03-23T00:00:02Z",
    });
    createImportDbLexiconJob.mockResolvedValue({
      id: "job-1",
      created_by: "user-1",
      job_type: "import_db",
      status: "running",
      target_key: "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      request_payload: {
        input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        source_type: "lexicon_snapshot",
        source_reference: "lexicon-20260321-wordfreq",
        language: "en",
        conflict_mode: "fail",
        error_mode: "continue",
        row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      },
      result_payload: null,
      progress_summary: {
        phase: "validating",
        total: 1,
        validated: 0,
        imported: 0,
        skipped: 0,
        failed: 0,
        to_validate: 1,
        to_import: 1,
      },
      progress_total: 1,
      progress_completed: 0,
      progress_current_label: "bank",
      error_message: null,
      created_at: "2026-03-23T00:00:00Z",
      started_at: "2026-03-23T00:00:01Z",
      completed_at: null,
    });
    listLexiconJobs.mockResolvedValue([]);
  });

  it("renders import dry-run and execute controls", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/import-db?inputPath=%2Fdata%2Flexicon%2Fsnapshots%2Fdemo%2Freviewed%2Fapproved.jsonl&sourceReference=lexicon-20260321-wordfreq&language=en",
    );
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-page")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Input path: /data/lexicon/snapshots/demo/reviewed/approved.jsonl",
    );
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Source reference: lexicon-20260321-wordfreq",
    );
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Stage: Final DB write",
    );
    expect(screen.getByText(/Use reviewed\/approved\.jsonl from Compiled Review export or JSONL Review materialize, not the raw words\.enriched\.jsonl artifact unless you are intentionally bypassing review\./)).toBeInTheDocument();
    expect(screen.getByText("Compiled artifact")).toBeInTheDocument();
    expect(screen.getByText("Reviewed directory")).toBeInTheDocument();
    expect(screen.getByText("Approved import input")).toBeInTheDocument();
    expect(screen.getAllByText("Decision ledger").length).toBeGreaterThan(0);
    expect(screen.getByTestId("lexicon-db-section-nav")).toHaveTextContent("Enrichment Import");
    expect(screen.getByTestId("lexicon-db-section-nav")).toHaveTextContent("DB Inspector");
    expect(screen.getByTestId("lexicon-import-db-form-grid")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("data/lexicon/snapshots/.../reviewed/approved.jsonl")).toBeInTheDocument();
    expect(screen.getByTestId("lexicon-import-db-conflict-mode")).toHaveValue("fail");
    expect(dryRunLexiconImport).not.toHaveBeenCalled();
    await user.type(screen.getByTestId("lexicon-import-db-input-path"), "data/lexicon/snapshots/demo/words.enriched.jsonl");
    await user.click(screen.getByTestId("lexicon-import-db-dry-run-button"));

    await waitFor(() => expect(dryRunLexiconImport).toHaveBeenCalled());
    await user.click(screen.getByTestId("lexicon-import-db-run-button"));

    await waitFor(() => expect(createImportDbLexiconJob).toHaveBeenCalledWith({
      inputPath: expect.stringContaining("/data/lexicon/snapshots/demo/reviewed/approved.jsonl"),
      sourceType: "lexicon_snapshot",
      sourceReference: "lexicon-20260321-wordfreq",
      language: "en",
      conflictMode: "fail",
      errorMode: "continue",
    }));
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: bank");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("To validate");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Validated");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("To import");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Imported");
  });

  it("shows failed-before-first-row copy instead of waiting text", async () => {
    getLexiconJob.mockResolvedValue({
      id: "job-failed",
      created_by: "user-1",
      job_type: "import_db",
      status: "failed",
      target_key: "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      request_payload: {
        input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        source_type: "lexicon_snapshot",
        source_reference: "lexicon-20260321-wordfreq",
        language: "en",
        conflict_mode: "fail",
        error_mode: "continue",
        row_summary: { row_count: 1, word_count: 0, phrase_count: 1, reference_count: 0 },
      },
      result_payload: null,
      progress_total: 0,
      progress_completed: 0,
      progress_current_label: "Failed before first row",
      error_message: "sense 2 translations.zh-Hans.usage_note must be a non-empty string",
      created_at: "2026-03-23T00:00:00Z",
      started_at: "2026-03-23T00:00:01Z",
      completed_at: "2026-03-23T00:00:02Z",
    });
    window.localStorage.setItem("lexicon-import-db-active-job", "job-failed");
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-progress")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: Failed before first row");
    expect(screen.queryByText("Waiting for first row...")).not.toBeInTheDocument();
    expect(screen.getByText(/usage_note/)).toBeInTheDocument();
  });

  it("preserves backend failure labels for zero-row failures", async () => {
    getLexiconJob.mockResolvedValue({
      id: "job-preflight-failed",
      created_by: "user-1",
      job_type: "import_db",
      status: "failed",
      target_key: "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      request_payload: {
        input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        source_type: "lexicon_snapshot",
        source_reference: "lexicon-20260321-wordfreq",
        language: "en",
        conflict_mode: "fail",
        error_mode: "continue",
        row_summary: { row_count: 3, word_count: 0, phrase_count: 3, reference_count: 0 },
      },
      result_payload: null,
      progress_summary: {
        phase: "failed",
        total: 3,
        validated: 2,
        imported: 0,
        skipped: 0,
        failed: 0,
        to_validate: 1,
        to_import: 3,
      },
      progress_total: 3,
      progress_completed: 0,
      progress_current_label: "Validating 2/3: fuss over",
      error_message: "sense 2 translations.zh-Hans.usage_note must be a non-empty string",
      created_at: "2026-03-23T00:00:00Z",
      started_at: "2026-03-23T00:00:01Z",
      completed_at: "2026-03-23T00:00:02Z",
    });
    window.localStorage.setItem("lexicon-import-db-active-job", "job-preflight-failed");
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-progress")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: Validating 2/3: fuss over");
    expect(screen.queryByText("Current entry: Failed before first row")).not.toBeInTheDocument();
  });

  it("reconnects to the active import job from local storage", async () => {
    window.localStorage.setItem("lexicon-import-db-active-job", "job-1");
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(getLexiconJob).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Validated1"));
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: Completed");
  });

  it("shows the last completed import job in recent jobs when there is no active key", async () => {
    window.localStorage.setItem("lexicon-import-db-last-job", "job-1");
    listLexiconJobs.mockResolvedValue([
      {
        id: "job-1",
        created_by: "user-1",
        job_type: "import_db",
        status: "completed",
        target_key: "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        request_payload: {
          input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
          source_reference: "lexicon-20260321-wordfreq",
          conflict_mode: "fail",
          error_mode: "continue",
        },
      result_payload: { created_words: 1 },
      progress_summary: {
        phase: "completed",
        total: 1,
        validated: 1,
        imported: 1,
        skipped: 0,
        failed: 0,
        to_validate: 0,
        to_import: 0,
      },
      progress_total: 1,
        progress_completed: 1,
        progress_current_label: "bank",
        error_message: null,
        created_at: "2026-03-23T00:00:00Z",
        started_at: "2026-03-23T00:00:01Z",
        completed_at: "2026-03-23T00:00:02Z",
      },
    ]);
    render(<LexiconImportDbPage />);

    expect(screen.queryByTestId("lexicon-import-db-progress")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("completed");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("approved.jsonl");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("Current entry: Completed");
  });

  it("renders recent jobs with failed status emphasis", async () => {
    listLexiconJobs.mockResolvedValue([
      {
        id: "job-failed",
        created_by: "user-1",
        job_type: "import_db",
        status: "failed",
        target_key: "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        request_payload: {
          input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
          conflict_mode: "skip",
          error_mode: "continue",
        },
      result_payload: { skipped_words: 1, failed_rows: 1 },
      progress_summary: {
        phase: "failed",
        total: 10,
        validated: 10,
        imported: 3,
        skipped: 1,
        failed: 1,
        to_validate: 0,
        to_import: 5,
      },
      progress_total: 10,
        progress_completed: 4,
        progress_current_label: null,
        error_message: "usage_note must be a non-empty string",
        created_at: "2026-03-23T00:00:00Z",
        started_at: "2026-03-23T00:00:01Z",
        completed_at: "2026-03-23T00:00:02Z",
      },
    ]);

    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("Recent jobs");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("failed");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("approved.jsonl");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("usage_note");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("Current entry: Failed after 4/10");
  });

  it("expands recent jobs when more than the inline limit exists", async () => {
    listLexiconJobs.mockResolvedValue(
      Array.from({ length: 8 }, (_, index) => ({
        id: `job-${index + 1}`,
        created_by: "user-1",
        job_type: "import_db",
        status: "completed",
        target_key: `import_db:/data/lexicon/snapshots/demo/reviewed/approved-${index + 1}.jsonl`,
        request_payload: {
          input_path: `/data/lexicon/snapshots/demo/reviewed/approved-${index + 1}.jsonl`,
          conflict_mode: "fail",
          error_mode: "continue",
        },
        result_payload: { created_words: index + 1 },
        progress_summary: {
          phase: "completed",
          total: 1,
          validated: 1,
          imported: 1,
          skipped: 0,
          failed: 0,
          to_validate: 0,
          to_import: 0,
        },
        progress_total: 1,
        progress_completed: 1,
        progress_current_label: `entry-${index + 1}`,
        error_message: null,
        created_at: "2026-03-23T00:00:00Z",
        started_at: "2026-03-23T00:00:01Z",
        completed_at: "2026-03-23T00:00:02Z",
      })),
    );

    const user = userEvent.setup();
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toBeInTheDocument());
    expect(screen.getByText("/data/lexicon/snapshots/demo/reviewed/approved-1.jsonl")).toBeInTheDocument();
    expect(screen.getByText("/data/lexicon/snapshots/demo/reviewed/approved-6.jsonl")).toBeInTheDocument();
    expect(screen.queryByText("/data/lexicon/snapshots/demo/reviewed/approved-7.jsonl")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show all recent jobs" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show all recent jobs" }));

    expect(screen.getByText("/data/lexicon/snapshots/demo/reviewed/approved-7.jsonl")).toBeInTheDocument();
    expect(screen.getByText("/data/lexicon/snapshots/demo/reviewed/approved-8.jsonl")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show fewer recent jobs" })).toBeInTheDocument();
  });
});
