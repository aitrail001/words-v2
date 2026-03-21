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
    render(<LexiconImportDbPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-import-db-page")).toBeInTheDocument());
    await user.type(screen.getByTestId("lexicon-import-db-input-path"), "data/lexicon/snapshots/demo/words.enriched.jsonl");
    await user.click(screen.getByTestId("lexicon-import-db-dry-run-button"));

    await waitFor(() => expect(dryRunLexiconImport).toHaveBeenCalled());
    await user.click(screen.getByTestId("lexicon-import-db-run-button"));

    await waitFor(() => expect(runLexiconImport).toHaveBeenCalled());
  });
});
