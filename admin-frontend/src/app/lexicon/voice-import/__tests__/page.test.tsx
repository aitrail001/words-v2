import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconVoiceImportPage from "@/app/lexicon/voice-import/page";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { dryRunVoiceImport } from "@/lib/lexicon-imports-client";
import { createVoiceImportDbLexiconJob, getLexiconJob, listLexiconJobs } from "@/lib/lexicon-jobs-client";

jest.mock("@/lib/auth-session", () => ({ readAccessToken: jest.fn() }));
jest.mock("@/lib/auth-redirect", () => ({ redirectToLogin: jest.fn() }));
jest.mock("@/lib/lexicon-imports-client", () => ({ dryRunVoiceImport: jest.fn() }));
jest.mock("@/lib/lexicon-jobs-client", () => ({
  createVoiceImportDbLexiconJob: jest.fn(),
  getLexiconJob: jest.fn(),
  listLexiconJobs: jest.fn(),
}));

describe("LexiconVoiceImportPage", () => {
  const mockReadAccessToken = readAccessToken as jest.Mock;
  const mockRedirectToLogin = redirectToLogin as jest.Mock;
  const mockDryRunVoiceImport = dryRunVoiceImport as jest.Mock;
  const mockCreateVoiceImportDbLexiconJob = createVoiceImportDbLexiconJob as jest.Mock;
  const mockGetLexiconJob = getLexiconJob as jest.Mock;
  const mockListLexiconJobs = listLexiconJobs as jest.Mock;

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
    mockCreateVoiceImportDbLexiconJob.mockResolvedValue({
      id: "job-1",
      created_by: null,
      job_type: "voice_import_db",
      status: "running",
      target_key: "voice_import_db:/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl",
      request_payload: { input_path: "/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl" },
      result_payload: null,
      progress_total: 2,
      progress_completed: 1,
      progress_current_label: "Importing 1/2: bank",
      progress_summary: {
        phase: "importing",
        total: 2,
        validated: 2,
        imported: 1,
        skipped: 0,
        failed: 0,
        to_validate: 0,
        to_import: 1,
      },
      error_message: null,
      created_at: "2026-03-30T10:00:00Z",
      started_at: "2026-03-30T10:00:01Z",
      completed_at: null,
    });
    mockGetLexiconJob.mockResolvedValue({
      id: "job-1",
      created_by: null,
      job_type: "voice_import_db",
      status: "completed",
      target_key: "voice_import_db:/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl",
      request_payload: { input_path: "/data/lexicon/voice/voice-roundtrip/voice_manifest.jsonl" },
      result_payload: { created_assets: 2, skipped_rows: 0, failed_rows: 0 },
      progress_total: 2,
      progress_completed: 2,
      progress_current_label: "Completed",
      progress_summary: {
        phase: "completed",
        total: 2,
        validated: 2,
        imported: 2,
        skipped: 0,
        failed: 0,
        to_validate: 0,
        to_import: 0,
      },
      error_message: null,
      created_at: "2026-03-30T10:00:00Z",
      started_at: "2026-03-30T10:00:01Z",
      completed_at: "2026-03-30T10:00:02Z",
    });
    mockListLexiconJobs.mockResolvedValue([
      {
        id: "job-recent",
        created_by: null,
        job_type: "voice_import_db",
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
        error_message: "voice asset already exists",
        created_at: "2026-03-30T09:00:00Z",
        started_at: "2026-03-30T09:00:01Z",
        completed_at: "2026-03-30T09:00:02Z",
      },
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
    await user.click(screen.getByTestId("lexicon-voice-import-dry-run"));

    await waitFor(() => expect(mockDryRunVoiceImport).toHaveBeenCalled());
    expect(screen.getByTestId("lexicon-voice-import-result")).toHaveTextContent("Rows");
    expect(screen.getByTestId("lexicon-voice-import-result")).toHaveTextContent("Generated");
    expect(screen.getByTestId("lexicon-voice-import-recent-jobs")).toHaveTextContent("voice asset already exists");
  });

  it("starts a background job and renders import progress", async () => {
    const user = userEvent.setup();
    render(<LexiconVoiceImportPage />);

    await user.click(await screen.findByTestId("lexicon-voice-import-run"));

    await waitFor(() => expect(mockCreateVoiceImportDbLexiconJob).toHaveBeenCalled());
    expect(screen.getByTestId("lexicon-voice-import-progress")).toHaveTextContent("Current entry: Importing 1/2: bank");
    expect(screen.getByTestId("lexicon-voice-import-progress")).toHaveTextContent("Imported");
  });
});
