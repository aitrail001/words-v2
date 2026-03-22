import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconDbInspectorPage from "@/app/lexicon/db-inspector/page";
import { browseLexiconInspectorEntries, getLexiconInspectorDetail } from "@/lib/lexicon-inspector-client";

jest.mock("@/lib/lexicon-inspector-client", () => ({
  browseLexiconInspectorEntries: jest.fn(),
  getLexiconInspectorDetail: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconDbInspectorPage", () => {
  const mockBrowse = browseLexiconInspectorEntries as jest.Mock;
  const mockDetail = getLexiconInspectorDetail as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockBrowse.mockResolvedValue({
      items: [
        {
          id: "word-1",
          family: "word",
          display_text: "bank",
          normalized_form: "bank",
          language: "en",
          source_reference: "snapshot-001",
          cefr_level: "B1",
          frequency_rank: 100,
          secondary_label: "bæŋk",
          created_at: "2026-03-21T00:00:00Z",
        },
        {
          id: "phrase-1",
          family: "phrase",
          display_text: "break a leg",
          normalized_form: "break a leg",
          language: "en",
          source_reference: "snapshot-001",
          cefr_level: "B2",
          frequency_rank: null,
          secondary_label: "idiom",
          created_at: "2026-03-20T00:00:00Z",
        },
      ],
      total: 2,
      family: "all",
      q: null,
      limit: 25,
      offset: 0,
      has_more: false,
    });
    mockDetail.mockResolvedValue({
      family: "word",
      id: "word-1",
      display_text: "bank",
      normalized_form: "bank",
      language: "en",
      cefr_level: "B1",
      frequency_rank: 100,
      phonetic: "bæŋk",
      phonetic_source: "lexicon_snapshot",
      source_reference: "snapshot-001",
      created_at: "2026-03-21T00:00:00Z",
      meanings: [],
      enrichment_runs: [],
    });
  });

  it("renders browse filters and loads detail for the selected entry", async () => {
    const user = userEvent.setup();
    window.history.pushState({}, "", "/lexicon/db-inspector?snapshot=words-100-20260312");
    render(<LexiconDbInspectorPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-db-inspector-page")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-db-inspector-context")).toHaveTextContent("Snapshot: words-100-20260312");
    await waitFor(() =>
      expect(mockBrowse).toHaveBeenCalledWith({
        family: "all",
        sort: "updated_desc",
        limit: 25,
        offset: 0,
        q: undefined,
      }),
    );
    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith("word", "word-1"));

    await user.selectOptions(screen.getByTestId("lexicon-db-inspector-family-filter"), "phrase");
    await waitFor(() =>
      expect(mockBrowse).toHaveBeenLastCalledWith({
        family: "phrase",
        sort: "updated_desc",
        limit: 25,
        offset: 0,
        q: undefined,
      }),
    );

    await user.type(screen.getByTestId("lexicon-db-inspector-search-input"), "bank");
    await waitFor(() =>
      expect(mockBrowse).toHaveBeenLastCalledWith({
        family: "phrase",
        sort: "updated_desc",
        limit: 25,
        offset: 0,
        q: "bank",
      }),
    );
  });
});
