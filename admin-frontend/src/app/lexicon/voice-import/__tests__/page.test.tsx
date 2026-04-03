import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconVoiceImportPage from "@/app/lexicon/voice-import/page";
import { ApiError } from "@/lib/api-client";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { dryRunVoiceImport } from "@/lib/lexicon-imports-client";
import { createVoiceImportDbLexiconJob, getLexiconJob, listLexiconJobs } from "@/lib/lexicon-jobs-client";

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(),
  readRefreshToken: jest.fn(() => null),
}));
jest.mock("@/lib/auth-redirect", () => ({ redirectToLogin: jest.fn() }));
jest.mock("@/lib/lexicon-imports-client", () => ({ dryRunVoiceImport: jest.fn() }));
jest.mock("@/lib/lexicon-jobs-client", () => ({
  addLexiconActiveJobId: jest.requireActual("@/lib/lexicon-jobs-client").addLexiconActiveJobId,
  createVoiceImportDbLexiconJob: jest.fn(),
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

describe("LexiconVoiceImportPage", () => {
  const mockReadAccessToken = readAccessToken as jest.Mock;
  const mockRedirectToLogin = redirectToLogin as jest.Mock;
  const mockDryRunVoiceImport = dryRunVoiceImport as jest.Mock;
  const mockCreateVoiceImportDbLexiconJob = createVoiceImportDbLexiconJob as jest.Mock;
  const mockGetLexiconJob = getLexiconJob as jest.Mock;
  const mockListLexiconJobs = listLexiconJobs as jest.Mock;

  const buildVoiceJob = (overrides: any = {}) => ({
    id: overrides.id ?? "job-1",
    created_by: overrides.created_by ?? null,
    job_type: "voice_import_db",
    status: overrides.status ?? "running",
    target_key: overrides.target_key ?? "voice_import_db:/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl",
    request_payload: {
      input_path: "/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl",
      ...(overrides.request_payload ?? {}),
    },
    result_payload: overrides.result_payload ?? null,
    progress_total: overrides.progress_total ?? 2,
    progress_completed: overrides.progress_completed ?? 1,
    progress_current_label: overrides.progress_current_label ?? "Importing 1/2: bank",
    progress_summary: overrides.progress_summary === null
      ? null
      : {
          phase: "importing",
          total: 2,
          validated: 2,
          imported: 1,
          skipped: 0,
          failed: 0,
          to_validate: 0,
          to_import: 1,
          ...(overrides.progress_summary ?? {}),
        },
    progress_timing: overrides.progress_timing === null
      ? null
      : {
          elapsed_ms: 4200,
          validation_elapsed_ms: 1700,
          import_elapsed_ms: 2100,
          queue_wait_ms: 400,
          ...(overrides.progress_timing ?? {}),
        },
    error_message: overrides.error_message ?? null,
    created_at: overrides.created_at ?? "2026-03-30T10:00:00Z",
    started_at: overrides.started_at ?? "2026-03-30T10:00:01Z",
    completed_at: overrides.completed_at ?? null,
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockReadAccessToken.mockReturnValue("active-token");
    mockDryRunVoiceImport.mockResolvedValue({
      artifact_filename: "voice_manifest.jsonl",
      input_path: "/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl",
      row_summary: { row_count: 2, generated_count: 2, existing_count: 0, failed_count: 0 },
      import_summary: { dry_run: 1, failed_rows: 0 },
      error_samples: [],
    });
    mockCreateVoiceImportDbLexiconJob.mockResolvedValue(buildVoiceJob());
    mockGetLexiconJob.mockResolvedValue(
      buildVoiceJob({
        status: "completed",
        progress_completed: 2,
        progress_current_label: "Completed",
        progress_summary: { phase: "completed", validated: 2, imported: 2, to_validate: 0, to_import: 0 },
        result_payload: { created_assets: 2, skipped_rows: 0, failed_rows: 0 },
        completed_at: "2026-03-30T10:00:02Z",
      }),
    );
    mockListLexiconJobs.mockResolvedValue([
      buildVoiceJob({
        id: "job-recent",
        status: "failed",
        target_key: "voice_import_db:/data/lexicon/voice/voice-old/voice_manifest.jsonl",
        request_payload: { input_path: "/data/lexicon/voice/voice-old/voice_manifest.jsonl" },
        result_payload: { failed_rows: 1, skipped_rows: 0 },
        progress_total: 1,
        progress_completed: 0,
        progress_current_label: "Failed before first row",
        progress_summary: {
          phase: "failed",
          total: 1,
          validated: 0,
          imported: 0,
          skipped: 0,
          failed: 1,
          to_validate: 1,
          to_import: 1,
        },
        progress_timing: { elapsed_ms: 1800, validation_elapsed_ms: 900, import_elapsed_ms: 0, queue_wait_ms: 250 },
        error_message: "voice asset already exists",
        created_at: "2026-03-30T09:00:00Z",
        started_at: "2026-03-30T09:00:01Z",
        completed_at: "2026-03-30T09:00:02Z",
      }),
    ]);
    window.history.pushState({}, "", "/lexicon/voice-import?inputPath=%2Fdata%2Flexicon%2Fvoice%2Fvoice-roundtrip%2Fvoice_manifest.jsonl");
    window.localStorage.clear();
  });

  it("redirects unauthenticated users to login", async () => {
    mockReadAccessToken.mockReturnValue(null);
    render(<LexiconVoiceImportPage />);
    await waitFor(() => expect(mockRedirectToLogin).toHaveBeenCalledWith("/lexicon/voice-import"));
  });

  it("prefills the manifest path and renders dry-run and recent job details", async () => {
    const user = userEvent.setup();
    render(<LexiconVoiceImportPage />);

    expect(await screen.findByTestId("lexicon-voice-import-input-path")).toHaveValue("/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl");
    expect(screen.getByTestId("lexicon-voice-import-conflict-mode")).toHaveValue("fail");
    expect(screen.getByTestId("lexicon-voice-import-section-nav")).toHaveTextContent("Storage");
    expect(screen.getByTestId("lexicon-voice-import-section-nav")).toHaveTextContent("Voice Runs");
    expect(screen.getByTestId("lexicon-voice-import-section-nav")).toHaveTextContent("Voice DB Import");
    expect(screen.getByTestId("lexicon-voice-import-form-grid")).toBeInTheDocument();

    await user.click(screen.getByTestId("lexicon-voice-import-dry-run"));

    await waitFor(() => expect(mockDryRunVoiceImport).toHaveBeenCalled());
    expect(screen.getByTestId("lexicon-voice-import-result")).toHaveTextContent("Rows");
    expect(screen.getByTestId("lexicon-voice-import-result")).toHaveTextContent("Generated");
    expect(screen.getByTestId("lexicon-voice-import-recent-jobs")).toHaveTextContent("voice asset already exists");
    expect(screen.getByTestId("lexicon-voice-import-recent-jobs")).toHaveTextContent("Elapsed");
  });

  it("renders multiple active voice jobs from local storage", async () => {
    window.localStorage.setItem("lexicon-voice-import-active-jobs", JSON.stringify(["job-1", "job-2"]));
    mockGetLexiconJob.mockImplementation((jobId: string) => Promise.resolve(
      jobId === "job-1"
        ? buildVoiceJob({ id: "job-1", progress_current_label: "Importing 1/2: bank" })
        : buildVoiceJob({
            id: "job-2",
            status: "queued",
            progress_completed: 0,
            progress_current_label: null,
            request_payload: { input_path: "/data/lexicon/voice/voice-second/voice_manifest.jsonl" },
            progress_summary: { phase: "queued", validated: 0, imported: 0, to_validate: 2, to_import: 2 },
            progress_timing: { elapsed_ms: 700, validation_elapsed_ms: 0, import_elapsed_ms: 0, queue_wait_ms: 700 },
          }),
    ));

    render(<LexiconVoiceImportPage />);

    await waitFor(() => expect(screen.getAllByTestId("lexicon-voice-import-active-job")).toHaveLength(2));
    expect(screen.getByTestId("lexicon-voice-import-progress")).toHaveTextContent("Showing 2 queued or running voice import jobs.");
    expect(screen.getByTestId("lexicon-voice-import-progress")).toHaveTextContent("/data/lexicon/voice/voice-second/voice_manifest.jsonl");
    expect(screen.getByTestId("lexicon-voice-import-progress")).toHaveTextContent("Queue wait");
    expect(screen.getByTestId("lexicon-voice-import-recent-jobs")).toHaveTextContent("Recent jobs");
  });

  it("shows a clear lock conflict message when create returns 409", async () => {
    const user = userEvent.setup();
    mockCreateVoiceImportDbLexiconJob.mockRejectedValue(
      new ApiError(409, "source_reference voice-roundtrip is already locked by job job-4"),
    );

    render(<LexiconVoiceImportPage />);

    await user.click(await screen.findByTestId("lexicon-voice-import-run"));

    await waitFor(() => expect(screen.getByText(/another voice import job already holds this source reference lock/i)).toBeInTheDocument());
    expect(screen.getByText(/locked by job job-4/i)).toBeInTheDocument();
  });
});
