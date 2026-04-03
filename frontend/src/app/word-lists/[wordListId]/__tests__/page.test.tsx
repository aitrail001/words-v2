import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WordListDetailRoute from "@/app/word-lists/[wordListId]/page";
import {
  addWordListItem,
  bulkAddWordListEntries,
  bulkDeleteWordListItems,
  deleteWordList,
  getWordList,
  resolveEntries,
  updateWordList,
} from "@/lib/imports-client";
import { getUserPreferences } from "@/lib/user-preferences-client";
import { searchKnowledgeMap, updateKnowledgeEntryStatus } from "@/lib/knowledge-map-client";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("@/lib/imports-client", () => ({
  addWordListItem: jest.fn(),
  bulkAddWordListEntries: jest.fn(),
  bulkDeleteWordListItems: jest.fn(),
  deleteWordList: jest.fn(),
  deleteWordListItem: jest.fn(),
  getWordList: jest.fn(),
  resolveEntries: jest.fn(),
  updateWordList: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client", () => ({
  searchKnowledgeMap: jest.fn(),
  updateKnowledgeEntryStatus: jest.fn(),
}));

jest.mock("@/lib/user-preferences-client", () => ({
  getUserPreferences: jest.fn(),
}));

describe("WordListDetailRoute", () => {
  const mockAddWordListItem = addWordListItem as jest.Mock;
  const mockBulkAddWordListEntries = bulkAddWordListEntries as jest.Mock;
  const mockBulkDeleteWordListItems = bulkDeleteWordListItems as jest.Mock;
  const mockDeleteWordList = deleteWordList as jest.Mock;
  const mockGetWordList = getWordList as jest.Mock;
  const mockResolveEntries = resolveEntries as jest.Mock;
  const mockUpdateWordList = updateWordList as jest.Mock;
  const mockSearchKnowledgeMap = searchKnowledgeMap as jest.Mock;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.Mock;
  const mockGetUserPreferences = getUserPreferences as jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPreferences.mockResolvedValue({ show_translations_by_default: true });
    mockGetWordList.mockResolvedValue({
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
          translation: "弥补",
          primary_definition: "Compensate for something.",
          status: "learning",
          frequency_count: 2,
          added_at: "2026-04-02T00:00:00.000Z",
        },
      ],
    });
    window.confirm = jest.fn(() => true);
  });

  it("renders the dedicated detail route and supports management modal updates", async () => {
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

    render(await WordListDetailRoute({ params: Promise.resolve({ wordListId: "list-1" }) }));

    await waitFor(() => expect(screen.getByTestId("word-list-detail-title")).toHaveTextContent("My Import"));
    expect(screen.getByTestId("word-list-back-link")).toHaveAttribute("href", "/word-lists");
    expect(screen.getByTestId("word-list-translation-toggle")).toHaveTextContent("Hide Translation");
    expect(screen.getByText("Compensate for something.")).toBeInTheDocument();
    expect(screen.getByText("弥补")).toBeInTheDocument();

    await user.click(screen.getByTestId("word-list-manage-button"));
    await user.clear(screen.getByTestId("word-list-rename-input"));
    await user.type(screen.getByTestId("word-list-rename-input"), "Renamed Import");
    await user.type(screen.getByTestId("word-list-description-input"), "Updated description");
    await user.click(screen.getByTestId("word-list-rename-button"));

    await waitFor(() => {
      expect(mockUpdateWordList).toHaveBeenCalledWith("list-1", {
        name: "Renamed Import",
        description: "Updated description",
      });
      expect(screen.getByTestId("word-list-message")).toHaveTextContent("List updated");
    });
  });

  it("toggles translation visibility while keeping the definition visible", async () => {
    const user = userEvent.setup();

    render(await WordListDetailRoute({ params: Promise.resolve({ wordListId: "list-1" }) }));

    await waitFor(() => expect(screen.getByText("Compensate for something.")).toBeInTheDocument());
    expect(screen.getByText("弥补")).toBeInTheDocument();

    await user.click(screen.getByTestId("word-list-translation-toggle"));
    expect(screen.getByText("Compensate for something.")).toBeInTheDocument();
    expect(screen.queryByText("弥补")).not.toBeInTheDocument();
  });

  it("supports status changes, bulk add, manual add, and bulk remove", async () => {
    const user = userEvent.setup();
    mockGetWordList.mockReset();
    mockGetWordList
      .mockResolvedValueOnce({
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
            translation: "弥补",
            primary_definition: "Compensate for something.",
            status: "learning",
            frequency_count: 2,
            added_at: "2026-04-02T00:00:00.000Z",
          },
        ],
      })
      .mockResolvedValueOnce({
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
            translation: "弥补",
            primary_definition: "Compensate for something.",
            status: "known",
            frequency_count: 2,
            added_at: "2026-04-02T00:00:00.000Z",
          },
          {
            id: "item-2",
            entry_type: "word",
            entry_id: "word-2",
            display_text: "resilience",
            normalized_form: "resilience",
            browse_rank: 12,
            cefr_level: "B2",
            phrase_kind: null,
            part_of_speech: "noun",
            translation: "韧性",
            primary_definition: "The ability to recover quickly.",
            status: "undecided",
            frequency_count: 1,
            added_at: "2026-04-02T00:00:00.000Z",
          },
        ],
      });
    mockUpdateKnowledgeEntryStatus.mockResolvedValueOnce({
      entry_type: "phrase",
      entry_id: "phrase-1",
      status: "known",
    });
    mockResolveEntries.mockResolvedValueOnce({
      found_entries: [
        {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "make up for",
        },
      ],
      ambiguous_entries: [],
      not_found_count: 0,
    });
    mockBulkAddWordListEntries.mockResolvedValueOnce({
      id: "list-1",
      name: "My Import",
      user_id: "user-1",
      description: null,
      source_type: "epub",
      source_reference: "job-1",
      created_at: "2026-04-02T00:00:00.000Z",
      items: [],
    });
    mockSearchKnowledgeMap.mockResolvedValueOnce({
      items: [
        {
          entry_type: "word",
          entry_id: "word-2",
          display_text: "resilience",
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
      status: "undecided",
      frequency_count: 1,
      added_at: "2026-04-02T00:00:00.000Z",
    });
    mockBulkDeleteWordListItems.mockResolvedValueOnce(undefined);

    render(await WordListDetailRoute({ params: Promise.resolve({ wordListId: "list-1" }) }));

    await waitFor(() => expect(screen.getByTestId("word-list-detail-items")).toBeInTheDocument());

    await user.selectOptions(screen.getAllByRole("combobox")[0], "known");
    await waitFor(() => expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalled());

    await user.type(screen.getByTestId("word-list-editor-text"), '"make up for"');
    await user.click(screen.getByTestId("word-list-add-button"));
    await waitFor(() => expect(mockBulkAddWordListEntries).toHaveBeenCalled());

    await user.type(screen.getByTestId("word-list-manual-search-input"), "resilience");
    await user.click(screen.getByTestId("word-list-manual-search-button"));
    await waitFor(() => expect(screen.getByTestId("word-list-manual-results")).toHaveTextContent("resilience"));
    await user.click(screen.getByTestId("word-list-manual-add-word-2"));
    await waitFor(() => expect(mockAddWordListItem).toHaveBeenCalled());

    await waitFor(() => expect(screen.getByTestId("word-list-detail-items")).toHaveTextContent("resilience"));
    await user.click(screen.getByTestId("word-list-select-item-item-2"));
    await user.click(screen.getByTestId("word-list-bulk-remove-button"));
    await waitFor(() => expect(mockBulkDeleteWordListItems).toHaveBeenCalledWith("list-1", ["item-2"]));
  });

  it("deletes the word list from the management modal", async () => {
    const user = userEvent.setup();
    mockDeleteWordList.mockResolvedValueOnce(undefined);

    render(await WordListDetailRoute({ params: Promise.resolve({ wordListId: "list-1" }) }));

    await waitFor(() => expect(screen.getByTestId("word-list-manage-button")).toBeInTheDocument());
    await user.click(screen.getByTestId("word-list-manage-button"));
    await user.click(screen.getByTestId("word-list-delete-button"));

    await waitFor(() => {
      expect(mockDeleteWordList).toHaveBeenCalledWith("list-1");
      expect(mockPush).toHaveBeenCalledWith("/word-lists");
    });
  });
});
