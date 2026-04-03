import { apiClient } from "@/lib/api-client";
import {
  addWordListItem,
  bulkDeleteImportJobs,
  bulkDeleteWordListItems,
  bulkDeleteWordLists,
  createListFromImport,
  createEmptyWordList,
  createWordListImport,
  deleteImportJob,
  deleteWordList,
  deleteWordListItem,
  getImportEntries,
  getImportJob,
  getImportProgressPercent,
  getWordList,
  isImportJobTerminal,
  listImportJobs,
  listWordLists,
  updateWordList,
} from "@/lib/imports-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    post: jest.fn(),
    get: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));

describe("imports-client", () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("uploads epub with FormData and returns import job", async () => {
    mockApiClient.post.mockResolvedValueOnce({
      id: "job-1",
      status: "queued",
      total_items: 0,
      processed_items: 0,
    } as any);

    const file = new File(["fake epub"], "book.epub", {
      type: "application/epub+zip",
    });

    const result = await createWordListImport(file);

    expect(result.id).toBe("job-1");
    expect(mockApiClient.post).toHaveBeenCalledWith("/word-lists/import", expect.any(FormData));
  });

  it("loads import job by id", async () => {
    mockApiClient.get.mockResolvedValueOnce({ id: "job-2", status: "processing" } as any);
    const result = await getImportJob("job-2");
    expect(result.id).toBe("job-2");
    expect(mockApiClient.get).toHaveBeenCalledWith("/import-jobs/job-2");
  });

  it("lists recent import jobs", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "job-3", status: "completed" }] as any);
    const result = await listImportJobs();
    expect(result).toEqual([{ id: "job-3", status: "completed" }]);
    expect(mockApiClient.get).toHaveBeenCalledWith("/import-jobs?limit=20&status_view=all");
  });

  it("lists active import jobs", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "job-4", status: "processing" }] as any);
    await listImportJobs(10, "active");
    expect(mockApiClient.get).toHaveBeenCalledWith("/import-jobs?limit=10&status_view=active");
  });

  it("loads import review entries", async () => {
    mockApiClient.get.mockResolvedValueOnce({ total: 1, items: [] } as any);
    await getImportEntries("job-2", { sort: "book_frequency", limit: 50 });
    expect(mockApiClient.get).toHaveBeenCalledWith(
      "/import-jobs/job-2/entries?sort=book_frequency&limit=50",
    );
  });

  it("deletes one import job", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await deleteImportJob("job-2");
    expect(mockApiClient.delete).toHaveBeenCalledWith("/import-jobs/job-2");
  });

  it("bulk deletes import jobs", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await bulkDeleteImportJobs(["job-1", "job-2"]);
    expect(mockApiClient.delete).toHaveBeenCalledWith("/import-jobs", {
      job_ids: ["job-1", "job-2"],
    });
  });

  it("creates a list from selected import entries", async () => {
    mockApiClient.post.mockResolvedValueOnce({ id: "list-1", name: "Imported" } as any);
    await createListFromImport("job-1", {
      name: "Imported",
      selected_entries: [{ entry_type: "word", entry_id: "entry-1" }],
    });
    expect(mockApiClient.post).toHaveBeenCalledWith("/import-jobs/job-1/word-lists", {
      name: "Imported",
      selected_entries: [{ entry_type: "word", entry_id: "entry-1" }],
    });
  });

  it("loads word lists", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "list-1", name: "Imported" }] as any);
    const result = await listWordLists();
    expect(result).toEqual([{ id: "list-1", name: "Imported" }]);
    expect(mockApiClient.get).toHaveBeenCalledWith("/word-lists");
  });

  it("creates an empty word list", async () => {
    mockApiClient.post.mockResolvedValueOnce({ id: "list-2", name: "Fresh" } as any);
    await createEmptyWordList({ name: "Fresh", description: "Notes" });
    expect(mockApiClient.post).toHaveBeenCalledWith("/word-lists", {
      name: "Fresh",
      description: "Notes",
    });
  });

  it("loads word list detail with query params", async () => {
    mockApiClient.get.mockResolvedValueOnce({ id: "list-1", items: [] } as any);
    await getWordList("list-1", { q: "make", sort: "rank", order: "desc" });
    expect(mockApiClient.get).toHaveBeenCalledWith("/word-lists/list-1?q=make&sort=rank&order=desc");
  });

  it("updates a word list", async () => {
    mockApiClient.patch.mockResolvedValueOnce({ id: "list-1", name: "Renamed" } as any);
    await updateWordList("list-1", { name: "Renamed" });
    expect(mockApiClient.patch).toHaveBeenCalledWith("/word-lists/list-1", { name: "Renamed" });
  });

  it("deletes a word list", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await deleteWordList("list-1");
    expect(mockApiClient.delete).toHaveBeenCalledWith("/word-lists/list-1");
  });

  it("bulk deletes word lists", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await bulkDeleteWordLists(["list-1", "list-2"]);
    expect(mockApiClient.delete).toHaveBeenCalledWith("/word-lists", {
      word_list_ids: ["list-1", "list-2"],
    });
  });

  it("adds one generic list item", async () => {
    mockApiClient.post.mockResolvedValueOnce({ id: "item-1" } as any);
    await addWordListItem("list-1", {
      entry_type: "phrase",
      entry_id: "phrase-1",
      frequency_count: 2,
    });
    expect(mockApiClient.post).toHaveBeenCalledWith("/word-lists/list-1/items", {
      entry_type: "phrase",
      entry_id: "phrase-1",
      frequency_count: 2,
    });
  });

  it("deletes a word list item", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await deleteWordListItem("list-1", "item-1");
    expect(mockApiClient.delete).toHaveBeenCalledWith("/word-lists/list-1/items/item-1");
  });

  it("bulk deletes word list items", async () => {
    mockApiClient.delete.mockResolvedValueOnce(undefined as any);
    await bulkDeleteWordListItems("list-1", ["item-1", "item-2"]);
    expect(mockApiClient.delete).toHaveBeenCalledWith("/word-lists/list-1/items", {
      item_ids: ["item-1", "item-2"],
    });
  });

  it("calculates progress percentage safely", () => {
    expect(getImportProgressPercent({ total_items: 0, processed_items: 0 } as any)).toBe(0);
    expect(getImportProgressPercent({ total_items: 10, processed_items: 4 } as any)).toBe(40);
    expect(getImportProgressPercent({ total_items: 10, processed_items: 19 } as any)).toBe(100);
  });

  it("detects terminal statuses", () => {
    expect(isImportJobTerminal("completed")).toBe(true);
    expect(isImportJobTerminal("failed")).toBe(true);
    expect(isImportJobTerminal("processing")).toBe(false);
    expect(isImportJobTerminal("queued")).toBe(false);
  });
});
