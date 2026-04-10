import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconImportDbPage from "@/app/lexicon/import-db/page";
import { ApiError } from "@/lib/api-client";
import { createImportDbLexiconJob, getLexiconJob, listLexiconJobs } from "@/lib/lexicon-jobs-client";
import { dryRunLexiconImport } from "@/lib/lexicon-imports-client";

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
  readRefreshToken: jest.fn(() => null),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

jest.mock("@/lib/lexicon-imports-client", () => ({
  dryRunLexiconImport: jest.fn(),
}));

jest.mock("@/lib/lexicon-jobs-client", () => ({
  addLexiconActiveJobId: jest.requireActual("@/lib/lexicon-jobs-client").addLexiconActiveJobId,
  createImportDbLexiconJob: jest.fn(),
  formatLexiconJobDuration: jest.requireActual("@/lib/lexicon-jobs-client").formatLexiconJobDuration,
  getLexiconJob: jest.fn(),
  getLexiconJobConflictMessage: jest.requireActual("@/lib/lexicon-jobs-client").getLexiconJobConflictMessage,
  getLexiconJobProgressTiming: jest.requireActual("@/lib/lexicon-jobs-client").getLexiconJobProgressTiming,
  isLexiconJobActive: jest.requireActual("@/lib/lexicon-jobs-client").isLexiconJobActive,
  listLexiconJobs: jest.fn(),
  readLexiconActiveJobIds: jest.requireActual("@/lib/lexicon-jobs-client").readLexiconActiveJobIds,
  removeLexiconActiveJobId: jest.requireActual("@/lib/lexicon-jobs-client").removeLexiconActiveJobId,
  upsertLexiconJob: jest.requireActual("@/lib/lexicon-jobs-client").upsertLexiconJob,
  writeLexiconActiveJobIds: jest.requireActual("@/lib/lexicon-jobs-client").writeLexiconActiveJobIds,
}));

describe("LexiconImportDbPage", () => {
  const mockDryRunLexiconImport = dryRunLexiconImport as jest.Mock;
  const mockCreateImportDbLexiconJob = createImportDbLexiconJob as jest.Mock;
  const mockGetLexiconJob = getLexiconJob as jest.Mock;
  const mockListLexiconJobs = listLexiconJobs as jest.Mock;

  const buildImportJob = (overrides: any = {}) => ({
    id: overrides.id ?? "job-1",
    created_by: overrides.created_by ?? "user-1",
    job_type: "import_db",
    status: overrides.status ?? "running",
    target_key: overrides.target_key ?? "import_db:/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
    request_payload: {
      input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      source_type: "lexicon_snapshot",
      source_reference: "lexicon-20260321-wordfreq",
      language: "en",
      conflict_mode: "fail",
      error_mode: "continue",
      row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      ...(overrides.request_payload ?? {}),
    },
    result_payload: overrides.result_payload ?? null,
    progress_summary: overrides.progress_summary === null
      ? null
      : {
          phase: "validating",
          total: 1,
          validated: 0,
          imported: 0,
          skipped: 0,
          failed: 0,
          to_validate: 1,
          to_import: 1,
          ...(overrides.progress_summary ?? {}),
        },
    progress_timing: overrides.progress_timing === null
      ? null
      : {
          elapsed_ms: 2400,
          validation_elapsed_ms: 1600,
          import_elapsed_ms: 0,
          queue_wait_ms: 400,
          ...(overrides.progress_timing ?? {}),
        },
    progress_total: overrides.progress_total ?? 1,
    progress_completed: overrides.progress_completed ?? 0,
    progress_current_label: overrides.progress_current_label ?? "bank",
    error_message: overrides.error_message ?? null,
    created_at: overrides.created_at ?? "2026-03-23T00:00:00Z",
    started_at: overrides.started_at ?? "2026-03-23T00:00:01Z",
    completed_at: overrides.completed_at ?? null,
  });

  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    window.history.pushState(
      {},
      "",
      "/lexicon/import-db?inputPath=%2Fdata%2Flexicon%2Fsnapshots%2Fdemo%2Freviewed%2Fapproved.jsonl&sourceReference=lexicon-20260321-wordfreq&language=en",
    );

    mockDryRunLexiconImport.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      import_summary: { dry_run: 1, failed_rows: 0 },
      error_samples: [],
    });
    mockCreateImportDbLexiconJob.mockResolvedValue(buildImportJob());
    mockGetLexiconJob.mockResolvedValue(buildImportJob({ status: "completed", progress_completed: 1, completed_at: "2026-03-23T00:00:02Z", result_payload: { created_words: 1 }, progress_summary: { phase: "completed", validated: 1, imported: 1, to_validate: 0, to_import: 0 }, progress_current_label: "Completed" }));
    mockListLexiconJobs.mockResolvedValue([]);
  });

  it("renders import dry-run and execute controls", async () => {
    const user = userEvent.setup();
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-page")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Input path: /data/lexicon/snapshots/demo/reviewed/approved.jsonl",
    );
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Source reference: lexicon-20260321-wordfreq",
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

    await user.click(screen.getByTestId("lexicon-import-db-dry-run-button"));
    await waitFor(() => expect(mockDryRunLexiconImport).toHaveBeenCalled());

    await user.click(screen.getByTestId("lexicon-import-db-run-button"));
    await waitFor(() => expect(mockCreateImportDbLexiconJob).toHaveBeenCalledWith({
      inputPath: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      sourceType: "lexicon_snapshot",
      sourceReference: "lexicon-20260321-wordfreq",
      language: "en",
      conflictMode: "fail",
      errorMode: "continue",
      importExecutionMode: "continuation",
      importRowChunkSize: 250,
      importRowCommitSize: 250,
    }));

    expect(window.localStorage.getItem("lexicon-import-db-active-jobs")).toBe(JSON.stringify(["job-1"]));
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: bank");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Elapsed");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Queue wait");
  });

  it("renders multiple active jobs from local storage and keeps recent jobs visible", async () => {
    window.localStorage.setItem("lexicon-import-db-active-jobs", JSON.stringify(["job-1", "job-2"]));
    mockGetLexiconJob.mockImplementation((jobId: string) => Promise.resolve(
      jobId === "job-1"
        ? buildImportJob({ id: "job-1", progress_current_label: "bank" })
        : buildImportJob({
            id: "job-2",
            status: "queued",
            progress_current_label: null,
            request_payload: { input_path: "/data/lexicon/snapshots/demo/reviewed/approved-2.jsonl" },
            progress_timing: { elapsed_ms: 900, validation_elapsed_ms: 0, import_elapsed_ms: 0, queue_wait_ms: 900 },
          }),
    ));
    mockListLexiconJobs.mockResolvedValue([
      buildImportJob({
        id: "job-recent",
        status: "completed",
        progress_completed: 1,
        completed_at: "2026-03-23T00:00:02Z",
        progress_summary: { phase: "completed", validated: 1, imported: 1, to_validate: 0, to_import: 0 },
        progress_timing: { elapsed_ms: 3200, validation_elapsed_ms: 1600, import_elapsed_ms: 1300, queue_wait_ms: 300 },
        result_payload: { created_words: 1 },
      }),
    ]);

    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getAllByTestId("lexicon-import-db-active-job")).toHaveLength(2));
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Showing 2 queued or running import jobs.");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("/data/lexicon/snapshots/demo/reviewed/approved-2.jsonl");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Queue wait");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("Recent jobs");
    expect(screen.getByTestId("lexicon-import-db-recent-jobs")).toHaveTextContent("Elapsed");
  });

  it("keeps the dry-run result visible when an active job is already tracked", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("lexicon-import-db-active-jobs", JSON.stringify(["job-1"]));
    mockGetLexiconJob.mockResolvedValue(buildImportJob({ id: "job-1", progress_current_label: "bank" }));
    mockListLexiconJobs.mockResolvedValue([]);

    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-progress")).toBeInTheDocument());
    await user.click(screen.getByTestId("lexicon-import-db-dry-run-button"));

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-summary-rows")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-summary-rows")).toHaveTextContent("Rows");
    expect(screen.getByTestId("lexicon-import-db-summary-rows")).toHaveTextContent("1");
  });

  it("shows a clear lock conflict message when create returns 409", async () => {
    const user = userEvent.setup();
    mockCreateImportDbLexiconJob.mockRejectedValue(
      new ApiError(409, "source_reference lexicon-20260321-wordfreq is already locked by job job-9"),
    );

    render(<LexiconImportDbPage />);

    await user.click(await screen.findByTestId("lexicon-import-db-run-button"));

    await waitFor(() => expect(screen.getByText(/source_reference lexicon-20260321-wordfreq is already locked by job job-9/i)).toBeInTheDocument());
    expect(screen.getByText(/locked by job job-9/i)).toBeInTheDocument();
  });

  it("expands recent jobs when more than the inline limit exists", async () => {
    mockListLexiconJobs.mockResolvedValue(
      Array.from({ length: 8 }, (_, index) => buildImportJob({
        id: `job-${index + 1}`,
        status: "completed",
        target_key: `import_db:/data/lexicon/snapshots/demo/reviewed/approved-${index + 1}.jsonl`,
        request_payload: {
          input_path: `/data/lexicon/snapshots/demo/reviewed/approved-${index + 1}.jsonl`,
          conflict_mode: "fail",
          error_mode: "continue",
        },
        result_payload: { created_words: index + 1 },
        progress_completed: 1,
        progress_summary: { phase: "completed", validated: 1, imported: 1, skipped: 0, failed: 0, to_validate: 0, to_import: 0, total: 1 },
        progress_current_label: `entry-${index + 1}`,
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
