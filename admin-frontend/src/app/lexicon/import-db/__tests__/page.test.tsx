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
  runLexiconImport: jest.fn(),
}));

describe("LexiconImportDbPage", () => {
  const { dryRunLexiconImport, runLexiconImport } = require("@/lib/lexicon-imports-client");

  beforeEach(() => {
    jest.clearAllMocks();
    dryRunLexiconImport.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      import_summary: null,
    });
    runLexiconImport.mockResolvedValue({
      artifact_filename: "words.enriched.jsonl",
      row_summary: { row_count: 1, word_count: 1, phrase_count: 0, reference_count: 0 },
      import_summary: { created_words: 1 },
    });
  });

  it("renders import dry-run and execute controls", async () => {
    const user = userEvent.setup();
    window.history.pushState(
      {},
      "",
      "/lexicon/import-db?inputPath=%2Fdata%2Flexicon%2Fsnapshots%2Fdemo%2Fapproved.jsonl&sourceReference=lexicon-20260321-wordfreq&language=en&autostart=1",
    );
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-page")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Input path: /data/lexicon/snapshots/demo/approved.jsonl",
    );
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Source reference: lexicon-20260321-wordfreq",
    );
    expect(screen.getByTestId("lexicon-import-db-context")).toHaveTextContent(
      "Stage: Final DB write",
    );
    expect(screen.getByText(/Use approved\.jsonl from Compiled Review export or JSONL Review materialize, not the raw words\.enriched\.jsonl artifact unless you are intentionally bypassing review\./)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("data/lexicon/snapshots/.../approved.jsonl")).toBeInTheDocument();
    await waitFor(() =>
      expect(dryRunLexiconImport).toHaveBeenCalledWith({
        inputPath: "/data/lexicon/snapshots/demo/approved.jsonl",
        sourceType: "lexicon_snapshot",
        sourceReference: "lexicon-20260321-wordfreq",
        language: "en",
      }),
    );
    await user.type(screen.getByTestId("lexicon-import-db-input-path"), "data/lexicon/snapshots/demo/words.enriched.jsonl");
    await user.click(screen.getByTestId("lexicon-import-db-dry-run-button"));

    await waitFor(() => expect(dryRunLexiconImport).toHaveBeenCalled());
    await user.click(screen.getByTestId("lexicon-import-db-run-button"));

    await waitFor(() => expect(runLexiconImport).toHaveBeenCalled());
  });
});
