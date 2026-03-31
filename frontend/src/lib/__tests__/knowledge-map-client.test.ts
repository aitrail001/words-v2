import {
  createKnowledgeMapSearchHistory,
  getKnowledgeMapDashboard,
  getKnowledgeMapEntryDetail,
  getKnowledgeMapList,
  getKnowledgeMapOverview,
  getKnowledgeMapRange,
  getKnowledgeMapSearchHistory,
  resolveLearnerVoicePlaybackUrl,
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
    jest.resetAllMocks();
  });

  it("loads the overview", async () => {
    mockApiClient.get.mockResolvedValueOnce({ bucket_size: 100, ranges: [] });

    const result = await getKnowledgeMapOverview();

    expect(result).toEqual({ bucket_size: 100, ranges: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/overview");
  });

  it("loads the dashboard summary", async () => {
    mockApiClient.get.mockResolvedValueOnce({ total_entries: 10 });

    const result = await getKnowledgeMapDashboard();

    expect(result).toEqual({ total_entries: 10 });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/dashboard");
  });

  it("loads a selected range", async () => {
    mockApiClient.get.mockResolvedValueOnce({ range_start: 101, items: [] });

    const result = await getKnowledgeMapRange(101);

    expect(result).toEqual({ range_start: 101, items: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith("/knowledge-map/ranges/101");
  });

  it("loads entry detail", async () => {
    mockApiClient.get.mockResolvedValueOnce({
      entry_id: "word-1",
      voice_assets: [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
      ],
    });

    const result = await getKnowledgeMapEntryDetail("word", "word-1");

    expect(result).toEqual({
      entry_id: "word-1",
      voice_assets: [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
      ],
    });
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

  it("loads a filtered learner list", async () => {
    mockApiClient.get.mockResolvedValueOnce({ items: [] });

    const result = await getKnowledgeMapList({
      status: "to_learn",
      q: "bank",
      sort: "rank_desc",
      limit: 20,
    });

    expect(result).toEqual({ items: [] });
    expect(mockApiClient.get).toHaveBeenCalledWith(
      "/knowledge-map/list?status=to_learn&q=bank&sort=rank_desc&limit=20",
    );
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

  it("resolves learner voice playback urls with accent fallback", () => {
    const voice = {
      preferred_locale: "us",
      preferred_playback_url: "/api/words/voice-assets/voice-us/content",
      locales: {
        us: {
          playback_url: "/api/words/voice-assets/voice-us/content",
          locale: "en_us",
        },
        uk: {
          playback_url: "/api/words/voice-assets/voice-uk/content",
          locale: "en_gb",
        },
      },
    };

    expect(resolveLearnerVoicePlaybackUrl(voice, "us")).toBe("/api/words/voice-assets/voice-us/content");
    expect(resolveLearnerVoicePlaybackUrl(voice, "uk")).toBe("/api/words/voice-assets/voice-uk/content");
    expect(
      resolveLearnerVoicePlaybackUrl(
        {
          preferred_locale: "au",
          preferred_playback_url: null,
          locales: {
            au: {
              playback_url: "/api/words/voice-assets/voice-au/content",
              locale: "en_au",
            },
          },
        },
        "uk",
      ),
    ).toBe("/api/words/voice-assets/voice-au/content");
    expect(resolveLearnerVoicePlaybackUrl(null, "us")).toBeNull();
  });
});
