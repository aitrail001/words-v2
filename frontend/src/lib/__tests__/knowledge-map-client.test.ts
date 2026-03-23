import {
  createKnowledgeMapSearchHistory,
  getKnowledgeMapEntryDetail,
  getKnowledgeMapOverview,
  getKnowledgeMapRange,
  getKnowledgeMapSearchHistory,
  searchKnowledgeMap,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
}));

describe("knowledge-map-client", () => {
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads the overview", async () => {
    mockApiClient.get.mockResolvedValueOnce({ bucket_size: 100, ranges: [] });

    const result = await getKnowledgeMapOverview();

    expect(result).toEqual({ bucket_size: 100, ranges: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/overview");
  });

  it("loads a selected range", async () => {
    mockApiClient.get.mockResolvedValueOnce({ range_start: 101, items: [] });

    const result = await getKnowledgeMapRange(101);

    expect(result).toEqual({ range_start: 101, items: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/ranges/101");
  });

  it("loads entry detail", async () => {
    mockApiClient.get.mockResolvedValueOnce({ entry_id: "word-1" });

    const result = await getKnowledgeMapEntryDetail("word", "word-1");

    expect(result).toEqual({ entry_id: "word-1" });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/entries/word/word-1");
  });

  it("updates entry status", async () => {
    mockApiClient.put.mockResolvedValueOnce({ status: "known" });

    const result = await updateKnowledgeEntryStatus("phrase", "phrase-1", "known");

    expect(result).toEqual({ status: "known" });
    expect(mockApiClient.put).toHaveBeenCalledWith(
      "/knowledge-map/entries/phrase/phrase-1/status",
      { status: "known" },
    );
  });

  it("searches the learner catalog", async () => {
    mockApiClient.get.mockResolvedValueOnce({ items: [] });

    const result = await searchKnowledgeMap("bank on");

    expect(result).toEqual({ items: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/search?q=bank%20on");
  });

  it("loads search history", async () => {
    mockApiClient.get.mockResolvedValueOnce({ items: [] });

    const result = await getKnowledgeMapSearchHistory();

    expect(result).toEqual({ items: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/search-history");
  });

  it("creates search history entries", async () => {
    mockApiClient.post.mockResolvedValueOnce({ query: "bank" });

    const result = await createKnowledgeMapSearchHistory({
      query: "bank",
      entry_type: "word",
      entry_id: "word-1",
    });

    expect(result).toEqual({ query: "bank" });
    expect(mockApiClient.post).toHaveBeenCalledWith("/knowledge-map/search-history", {
      query: "bank",
      entry_type: "word",
      entry_id: "word-1",
    });
  });
});
