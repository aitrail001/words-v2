import { apiClient } from "@/lib/api-client";
import {
  createWordListImport,
  getImportJob,
  getImportProgressPercent,
  isImportJobTerminal,
  listWordLists,
} from "@/lib/imports-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    post: jest.fn(),
    get: jest.fn(),
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

    const result = await createWordListImport(file, "My List");

    expect(result.id).toBe("job-1");
    expect(mockApiClient.post).toHaveBeenCalledWith(
      "/word-lists/import",
      expect.any(FormData),
    );

    const sentBody = mockApiClient.post.mock.calls[0][1] as FormData;
    expect(sentBody.get("list_name")).toBe("My List");
    expect((sentBody.get("file") as File).name).toBe("book.epub");
  });

  it("loads import job by id", async () => {
    mockApiClient.get.mockResolvedValueOnce({ id: "job-2", status: "processing" } as any);

    const result = await getImportJob("job-2");

    expect(result.id).toBe("job-2");
    expect(mockApiClient.get).toHaveBeenCalledWith("/import-jobs/job-2");
  });

  it("loads word lists", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "list-1", name: "Imported" }] as any);

    const result = await listWordLists();

    expect(result).toEqual([{ id: "list-1", name: "Imported" }]);
    expect(mockApiClient.get).toHaveBeenCalledWith("/word-lists");
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
