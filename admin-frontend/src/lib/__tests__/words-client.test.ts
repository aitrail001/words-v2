import { apiClient } from "@/lib/api-client";
import { getWordEnrichmentDetail, searchWords } from "@/lib/words-client";

jest.mock("@/lib/api-client", () => ({ apiClient: { get: jest.fn() } }));

describe("admin words-client", () => {
  const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;
  beforeEach(() => { jest.clearAllMocks(); });

  it("searches words with encoded query", async () => {
    mockApiClient.get.mockResolvedValueOnce([{ id: "word-1", word: "set" }] as any);
    const result = await searchWords("set up");
    expect(result).toEqual([{ id: "word-1", word: "set" }]);
    expect(mockApiClient.get).toHaveBeenCalledWith("/words/search?q=set%20up");
  });

  it("loads word enrichment detail", async () => {
    mockApiClient.get.mockResolvedValueOnce({ id: "word-1", meanings: [] } as any);
    const result = await getWordEnrichmentDetail("word-1");
    expect(result).toEqual({ id: "word-1", meanings: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/words/word-1/enrichment");
  });
});
