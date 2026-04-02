import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportsPage from "@/app/imports/page";
import {
  addWordListItem,
  bulkAddWordListEntries,
  createListFromImport,
  createWordListImport,
  deleteWordList,
  deleteWordListItem,
  getWordList,
  getImportEntries,
  listWordLists,
  resolveEntries,
  updateWordList,
} from "@/lib/imports-client";
import { searchKnowledgeMap } from "@/lib/knowledge-map-client";

jest.mock("@/lib/imports-client", () => ({
  addWordListItem: jest.fn(),
  bulkAddWordListEntries: jest.fn(),
  createWordListImport: jest.fn(),
  createListFromImport: jest.fn(),
  deleteWordList: jest.fn(),
  deleteWordListItem: jest.fn(),
  getWordList: jest.fn(),
  getImportEntries: jest.fn(),
  getImportJob: jest.fn(),
  listWordLists: jest.fn(),
  resolveEntries: jest.fn(),
  updateWordList: jest.fn(),
  getImportProgressPercent: jest.fn((job) => {
    if (!job.total_items) return 0;
    return Math.round((job.processed_items / job.total_items) * 100);
  }),
  isImportJobTerminal: jest.fn((status: string) => status === "completed" || status === "failed"),
}));

jest.mock("@/lib/knowledge-map-client", () => ({
  searchKnowledgeMap: jest.fn(),
}));

describe("ImportsPage", () => {
  const mockAddWordListItem = addWordListItem as jest.Mock;
  const mockBulkAddWordListEntries = bulkAddWordListEntries as jest.Mock;
  const mockCreateWordListImport = createWordListImport as jest.Mock;
  const mockCreateListFromImport = createListFromImport as jest.Mock;
  const mockDeleteWordList = deleteWordList as jest.Mock;
  const mockDeleteWordListItem = deleteWordListItem as jest.Mock;
  const mockGetWordList = getWordList as jest.Mock;
  const mockGetImportEntries = getImportEntries as jest.Mock;
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
    mockListWordLists.mockResolvedValue([]);
    mockSearchKnowledgeMap.mockResolvedValue({ items: [] });
    mockGetWordList.mockResolvedValue(detailResponse);
    mockGetImportEntries.mockResolvedValue({
      total: 2,
      items: [
        {
          entry_type: "word",
          entry_id: "word-1",
          display_text: "run",
          frequency_count: 3,
          browse_rank: 10,
          normalized_form: "run",
          cefr_level: "A1",
          phrase_kind: null,
        },
        {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "make up for",
          frequency_count: 2,
          browse_rank: 120,
          normalized_form: "make up for",
          cefr_level: "B2",
          phrase_kind: "phrasal_verb",
        },
      ],
    });
  });

  it("renders import form", async () => {
    render(<ImportsPage />);
    expect(screen.getByTestId("imports-page-title")).toBeInTheDocument();
    expect(screen.getByTestId("imports-upload-input")).toBeInTheDocument();
    expect(screen.getByTestId("imports-submit-button")).toBeInTheDocument();
    await waitFor(() => expect(mockListWordLists).toHaveBeenCalledTimes(1));
  });

  it("submits epub and renders review panel for completed import", async () => {
    const user = userEvent.setup();
    mockCreateWordListImport.mockResolvedValueOnce({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "book.epub",
      total_items: 2,
      processed_items: 2,
      created_at: "2026-04-02T00:00:00.000Z",
      word_list_id: null,
    });

    render(<ImportsPage />);

    const fileInput = screen.getByTestId("imports-upload-input") as HTMLInputElement;
    const file = new File(["epub content"], "book.epub", { type: "application/epub+zip" });

    await user.upload(fileInput, file);
    await user.click(screen.getByTestId("imports-submit-button"));

    await waitFor(() => {
      expect(mockCreateWordListImport).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("imports-review-panel")).toBeInTheDocument();
      expect(screen.getByTestId("imports-selected-count")).toHaveTextContent("2 selected");
    });
  });

  it("creates list from selected review entries", async () => {
    const user = userEvent.setup();
    mockCreateWordListImport.mockResolvedValueOnce({
      id: "job-1",
      status: "completed",
      list_name: "My Import",
      source_filename: "book.epub",
      total_items: 2,
      processed_items: 2,
      created_at: "2026-04-02T00:00:00.000Z",
      word_list_id: null,
    });
    mockCreateListFromImport.mockResolvedValueOnce({
      id: "list-1",
      name: "My Import",
      user_id: "user-1",
      description: null,
      source_type: "epub",
      source_reference: "job-1",
      created_at: "2026-04-02T00:00:00.000Z",
    });
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
    mockBulkAddWordListEntries.mockResolvedValueOnce(detailResponse);
    mockDeleteWordListItem.mockResolvedValueOnce(undefined);

    render(<ImportsPage />);

    const fileInput = screen.getByTestId("imports-upload-input") as HTMLInputElement;
    const file = new File(["epub content"], "book.epub", { type: "application/epub+zip" });
    await user.upload(fileInput, file);
    await user.click(screen.getByTestId("imports-submit-button"));

    await waitFor(() => expect(screen.getByTestId("imports-create-list-button")).toBeInTheDocument());
    await user.click(screen.getByTestId("imports-create-list-button"));

    await waitFor(() => {
      expect(mockCreateListFromImport).toHaveBeenCalledTimes(1);
      expect(mockCreateListFromImport).toHaveBeenCalledWith(
        "job-1",
        expect.objectContaining({ name: "My Import" }),
      );
      expect(
        within(screen.getByTestId("word-lists-list")).getByText("My Import"),
      ).toBeInTheDocument();
    });
  });

  it("opens a word list, removes an item, and bulk-adds resolved entries", async () => {
    const user = userEvent.setup();
    mockListWordLists.mockResolvedValueOnce([
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
    mockBulkAddWordListEntries.mockResolvedValueOnce(detailResponse);
    mockDeleteWordListItem.mockResolvedValueOnce(undefined);

    render(<ImportsPage />);

    await waitFor(() => expect(mockListWordLists).toHaveBeenCalledTimes(1));
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
    mockListWordLists.mockResolvedValueOnce([
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
    mockUpdateWordList.mockResolvedValueOnce({
      id: "list-1",
      name: "Renamed Import",
      user_id: "user-1",
      description: "Updated description",
      source_type: "epub",
      source_reference: "job-1",
      created_at: "2026-04-02T00:00:00.000Z",
    });
    mockGetWordList
      .mockResolvedValueOnce(detailResponse)
      .mockResolvedValueOnce({
        ...detailResponse,
        items: [],
      });
    mockSearchKnowledgeMap.mockResolvedValueOnce({
      items: [
        {
          entry_type: "word",
          entry_id: "word-9",
          display_text: "alpha",
          normalized_form: "alpha",
          browse_rank: 15,
          cefr_level: "A1",
          phrase_kind: null,
        },
      ],
    });
    mockAddWordListItem.mockResolvedValueOnce({
      id: "item-9",
      entry_type: "word",
      entry_id: "word-9",
      display_text: "alpha",
      normalized_form: "alpha",
      browse_rank: 15,
      cefr_level: "A1",
      phrase_kind: null,
      part_of_speech: "noun",
      frequency_count: 1,
      added_at: "2026-04-02T00:00:00.000Z",
    });
    mockDeleteWordList.mockResolvedValueOnce(undefined);

    render(<ImportsPage />);

    await waitFor(() => expect(mockListWordLists).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId("word-list-open-list-1"));

    await waitFor(() =>
      expect(screen.getByTestId("word-list-detail-title")).toHaveTextContent("My Import"),
    );

    await user.clear(screen.getByTestId("word-list-rename-input"));
    await user.type(screen.getByTestId("word-list-rename-input"), "Renamed Import");
    await user.clear(screen.getByTestId("word-list-description-input"));
    await user.type(screen.getByTestId("word-list-description-input"), "Updated description");
    await user.click(screen.getByTestId("word-list-rename-button"));

    await waitFor(() => {
      expect(mockUpdateWordList).toHaveBeenCalledWith("list-1", {
        name: "Renamed Import",
        description: "Updated description",
      });
      expect(screen.getByTestId("word-list-detail-title")).toHaveTextContent("Renamed Import");
    });

    await user.clear(screen.getByTestId("word-list-search-input"));
    await user.type(screen.getByTestId("word-list-search-input"), "alpha");
    await user.selectOptions(screen.getByTestId("word-list-sort-select"), "rank");

    await waitFor(() =>
      expect(mockGetWordList).toHaveBeenLastCalledWith("list-1", { q: "alpha", sort: "rank" }),
    );

    await user.clear(screen.getByTestId("word-list-manual-search-input"));
    await user.type(screen.getByTestId("word-list-manual-search-input"), "alpha");
    await user.click(screen.getByTestId("word-list-manual-search-button"));

    await waitFor(() =>
      expect(mockSearchKnowledgeMap).toHaveBeenCalledWith("alpha"),
    );
    await user.click(screen.getByTestId("word-list-manual-add-word-9"));

    await waitFor(() => {
      expect(mockAddWordListItem).toHaveBeenCalledWith("list-1", {
        entry_type: "word",
        entry_id: "word-9",
        frequency_count: 1,
      });
      expect(screen.getByTestId("word-list-detail-items")).toHaveTextContent("alpha");
    });

    await user.click(screen.getByTestId("word-list-view-tags"));
    expect(screen.getByTestId("word-list-tags-view")).toBeInTheDocument();
    await user.click(screen.getByTestId("word-list-view-list"));
    expect(screen.getByTestId("word-list-list-view")).toBeInTheDocument();

    await user.click(screen.getByTestId("word-list-delete-button"));
    await waitFor(() => {
      expect(mockDeleteWordList).toHaveBeenCalledWith("list-1");
      expect(screen.queryByTestId("word-list-detail-panel")).not.toBeInTheDocument();
    });
  });
});
