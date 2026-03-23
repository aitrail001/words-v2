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
}));

describe("LexiconImportDbPage", () => {
  const { dryRunLexiconImport } = require("@/lib/lexicon-imports-client");
  const { createImportDbLexiconJob, getLexiconJob } = require("@/lib/lexicon-jobs-client");

  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    dryRunLexiconImport.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      input_path: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
      row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      import_summary: null,
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
        row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      },
      result_payload: { created_words: 1 },
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
        row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      },
      result_payload: null,
      progress_total: 1,
      progress_completed: 0,
      progress_current_label: "bank",
      error_message: null,
      created_at: "2026-03-23T00:00:00Z",
      started_at: "2026-03-23T00:00:01Z",
      completed_at: null,
    });
  });

  it("renders import dry-run and execute controls", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/import-db?inputPath=%2Fdata%2Flexicon%2Fsnapshots%2Fdemo%2Freviewed%2Fapproved.jsonl&sourceReference=lexicon-20260321-wordfreq&language=en&autostart=1",
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
    expect(screen.getByPlaceholderText("data/lexicon/snapshots/.../reviewed/approved.jsonl")).toBeInTheDocument();
    await waitFor(() =>
      expect(dryRunLexiconImport).toHaveBeenCalledWith({
        inputPath: "/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
        sourceType: "lexicon_snapshot",
        sourceReference: "lexicon-20260321-wordfreq",
        language: "en",
      }),
    );
    await user.type(screen.getByTestId("lexicon-import-db-input-path"), "data/lexicon/snapshots/demo/words.enriched.jsonl");
    await user.click(screen.getByTestId("lexicon-import-db-dry-run-button"));

    await waitFor(() => expect(dryRunLexiconImport).toHaveBeenCalled());
    await user.click(screen.getByTestId("lexicon-import-db-run-button"));

    await waitFor(() => expect(createImportDbLexiconJob).toHaveBeenCalledWith({
      inputPath: expect.stringContaining("/data/lexicon/snapshots/demo/reviewed/approved.jsonl"),
      sourceType: "lexicon_snapshot",
      sourceReference: "lexicon-20260321-wordfreq",
      language: "en",
    }));
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: bank");
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("To do1");
  });

  it("reconnects to the active import job from local storage", async () => {
    window.localStorage.setItem("lexicon-import-db-active-job", "job-1");
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(getLexiconJob).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Done1"));
    expect(screen.getByTestId("lexicon-import-db-progress")).toHaveTextContent("Current entry: bank");
  });
});
