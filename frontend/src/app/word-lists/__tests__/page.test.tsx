import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WordListsPage from "@/app/word-lists/page";
import {
  addWordListItem,
  bulkAddWordListEntries,
  deleteWordList,
  deleteWordListItem,
  getWordList,
  listWordLists,
  resolveEntries,
  updateWordList,
} from "@/lib/imports-client";
import { searchKnowledgeMap } from "@/lib/knowledge-map-client";

jest.mock("@/lib/imports-client", () => ({
  addWordListItem: jest.fn(),
  bulkAddWordListEntries: jest.fn(),
  deleteWordList: jest.fn(),
  deleteWordListItem: jest.fn(),
  getWordList: jest.fn(),
  listWordLists: jest.fn(),
  resolveEntries: jest.fn(),
  updateWordList: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client", () => ({
  searchKnowledgeMap: jest.fn(),
}));

describe("WordListsPage", () => {
  const mockAddWordListItem = addWordListItem as jest.Mock;
  const mockBulkAddWordListEntries = bulkAddWordListEntries as jest.Mock;
  const mockDeleteWordList = deleteWordList as jest.Mock;
  const mockDeleteWordListItem = deleteWordListItem as jest.Mock;
  const mockGetWordList = getWordList as jest.Mock;
  const mockListWordLists = listWordLists as jest.Mock;
  const mockResolveEntries = resolveEntries as jest.Mock;
  const mockSearchKnowledgeMap = searchKnowledgeMap as jest.Mock;
  const mockUpdateWordList = updateWordList as jest.Mock;

  const detailResponse = {
    id: "list-1",
    name: "My Import",
    user_id: "user-1",
    description: null,
    source_type: "epub",
    source_reference: "job-1",
    created_at: "2026-04-02T00:00:00.000Z",
    items: [
      {
        id: "item-1",
        entry_type: "phrase",
        entry_id: "phrase-1",
        display_text: "make up for",
        normalized_form: "make up for",
        browse_rank: 120,
        cefr_level: "B2",
        phrase_kind: "phrasal_verb",
        part_of_speech: null,
        frequency_count: 2,
        added_at: "2026-04-02T00:00:00.000Z",
      },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockListWordLists.mockResolvedValue([
      {
        id: "list-1",
        name: "My Import",
        user_id: "user-1",
        description: null,
        source_type: "epub",
        source_reference: "job-1",
        created_at: "2026-04-02T00:00:00.000Z",
      },
    ]);
    mockSearchKnowledgeMap.mockResolvedValue({ items: [] });
    mockGetWordList.mockResolvedValue(detailResponse);
  });

  it("renders its own route with home/import navigation", async () => {
    render(await WordListsPage({}));

    expect(screen.getByTestId("word-lists-page-title")).toBeInTheDocument();
    expect(screen.getByTestId("word-lists-home-link")).toHaveAttribute("href", "/");
    expect(screen.getByTestId("word-lists-import-link")).toHaveAttribute("href", "/imports");
    await waitFor(() => expect(mockListWordLists).toHaveBeenCalledTimes(1));
  });

  it("opens a word list, removes an item, and bulk-adds resolved entries", async () => {
    const user = userEvent.setup();
    mockBulkAddWordListEntries.mockResolvedValueOnce(detailResponse);
    mockDeleteWordListItem.mockResolvedValueOnce(undefined);
    mockResolveEntries.mockResolvedValueOnce({
      found_entries: [
        {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "make up for",
          frequency_count: 1,
          browse_rank: 120,
          normalized_form: "make up for",
          cefr_level: "B2",
          phrase_kind: "phrasal_verb",
        },
      ],
      ambiguous_entries: [],
      not_found_count: 0,
    });

    render(await WordListsPage({}));

    await waitFor(() => expect(screen.getByTestId("word-list-open-list-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("word-list-open-list-1"));

    await waitFor(() =>
      expect(screen.getByTestId("word-list-detail-title")).toHaveTextContent("My Import"),
    );
    expect(screen.getByTestId("word-list-editor-help")).toHaveTextContent(
      "Enter one word per space, or quote multi-word phrases. You can also put one phrase per line.",
    );

    await user.click(screen.getByTestId("word-list-remove-item-1"));
    await waitFor(() =>
      expect(screen.getByTestId("word-list-detail-empty")).toBeInTheDocument(),
    );

    await user.type(screen.getByTestId("word-list-editor-text"), '"make up for"');
    await user.click(screen.getByTestId("word-list-add-button"));

    await waitFor(() => {
      expect(mockResolveEntries).toHaveBeenCalledWith('"make up for"');
      expect(mockBulkAddWordListEntries).toHaveBeenCalledWith(
        "list-1",
        expect.objectContaining({
          selected_entries: [{ entry_type: "phrase", entry_id: "phrase-1" }],
        }),
      );
      expect(screen.getByTestId("word-list-detail-items")).toHaveTextContent("make up for");
    });
  });

  it("renames, searches, adds one item, changes view mode, and deletes a word list", async () => {
    const user = userEvent.setup();
    mockUpdateWordList.mockResolvedValueOnce({
      id: "list-1",
      name: "Renamed Import",
      user_id: "user-1",
      description: "Updated description",
      source_type: "epub",
      source_reference: "job-1",
      created_at: "2026-04-02T00:00:00.000Z",
    });
    mockSearchKnowledgeMap.mockResolvedValueOnce({
      items: [
        {
          entry_type: "word",
          entry_id: "word-2",
          display_text: "resilience",
          browse_rank: 12,
          status: "to_learn",
        },
      ],
    });
    mockAddWordListItem.mockResolvedValueOnce({
      id: "item-2",
      entry_type: "word",
      entry_id: "word-2",
      display_text: "resilience",
      normalized_form: "resilience",
      browse_rank: 12,
      cefr_level: "B2",
      phrase_kind: null,
      part_of_speech: "noun",
      frequency_count: 1,
      added_at: "2026-04-02T00:00:00.000Z",
    });
    mockDeleteWordList.mockResolvedValueOnce(undefined);

    render(await WordListsPage({}));

    await waitFor(() => expect(screen.getByTestId("word-list-open-list-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("word-list-open-list-1"));
    await waitFor(() =>
      expect(screen.getByTestId("word-list-detail-title")).toHaveTextContent("My Import"),
    );

    await user.clear(screen.getByTestId("word-list-rename-input"));
    await user.type(screen.getByTestId("word-list-rename-input"), "Renamed Import");
    await user.type(screen.getByTestId("word-list-description-input"), "Updated description");
    await user.click(screen.getByTestId("word-list-rename-button"));

    await waitFor(() =>
      expect(screen.getByTestId("word-list-editor-message")).toHaveTextContent("List updated"),
    );

    await user.type(screen.getByTestId("word-list-search-input"), "make");
    await waitFor(() =>
      expect(mockGetWordList).toHaveBeenLastCalledWith("list-1", expect.objectContaining({ q: "make" })),
    );

    await user.clear(screen.getByTestId("word-list-manual-search-input"));
    await user.type(screen.getByTestId("word-list-manual-search-input"), "resilience");
    await user.click(screen.getByTestId("word-list-manual-search-button"));

    await waitFor(() =>
      expect(screen.getByTestId("word-list-manual-results")).toHaveTextContent("resilience"),
    );

    await user.click(screen.getByTestId("word-list-manual-add-word-2"));
    await waitFor(() =>
      expect(screen.getByTestId("word-list-manual-message")).toHaveTextContent("Added resilience"),
    );

    await user.click(screen.getByTestId("word-list-view-tags"));
    expect(screen.getByTestId("word-list-detail-items").className).toContain("flex");

    await user.click(screen.getByTestId("word-list-delete-button"));
    await waitFor(() =>
      expect(screen.getByTestId("word-lists-empty-state")).toBeInTheDocument(),
    );
  });
});
