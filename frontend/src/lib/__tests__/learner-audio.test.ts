import { apiClient } from "@/lib/api-client";
import { playLearnerEntryAudio } from "@/lib/learner-audio";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    getBlob: jest.fn(),
  },
}));

describe("learner-audio", () => {
  const mockGetBlob = apiClient.getBlob as jest.MockedFunction<typeof apiClient.getBlob>;
  const pause = jest.fn();
  const play = jest.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetBlob.mockResolvedValue(new Blob(["audio"], { type: "audio/mpeg" }));
    Object.defineProperty(global.URL, "createObjectURL", {
      configurable: true,
      value: jest.fn(() => "blob:audio"),
    });
    Object.defineProperty(global, "Audio", {
      configurable: true,
      value: jest.fn(() => ({
        pause,
        play,
        src: "",
      })),
    });
  });

  it("normalizes backend /api playback paths before calling ApiClient", async () => {
    const played = await playLearnerEntryAudio(
      [
        {
          id: "voice-1",
          content_scope: "word",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-1/content",
          relative_path: "learner/test/en_us.mp3",
        },
      ],
      "us",
    );

    expect(played).toBe(true);
    expect(mockGetBlob).toHaveBeenCalledWith("/words/voice-assets/voice-1/content");
  });
});
