import {
  detectDeviceTimezone,
  getUserPreferences,
  syncDetectedDeviceTimezone,
  updateUserPreferences,
} from "@/lib/user-preferences-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
  },
}));

describe("user-preferences-client", () => {
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads user preferences", async () => {
    mockApiClient.get.mockResolvedValueOnce({ accent_preference: "us" });

    const result = await getUserPreferences();

    expect(result).toEqual({ accent_preference: "us" });
    expect(mockApiClient.get).toHaveBeenCalledWith("/user-preferences");
  });

  it("updates user preferences", async () => {
    mockApiClient.put.mockResolvedValueOnce({ accent_preference: "au" });

    const result = await updateUserPreferences({
      accent_preference: "au",
      translation_locale: "es",
      knowledge_view_preference: "list",
      show_translations_by_default: false,
      review_depth_preset: "deep",
      timezone: "Australia/Melbourne",
      enable_confidence_check: false,
      enable_word_spelling: false,
      enable_audio_spelling: true,
      show_pictures_in_questions: true,
    });

    expect(result).toEqual({ accent_preference: "au" });
    expect(mockApiClient.put).toHaveBeenCalledWith("/user-preferences", {
      accent_preference: "au",
      translation_locale: "es",
      knowledge_view_preference: "list",
      show_translations_by_default: false,
      review_depth_preset: "deep",
      timezone: "Australia/Melbourne",
      enable_confidence_check: false,
      enable_word_spelling: false,
      enable_audio_spelling: true,
      show_pictures_in_questions: true,
    });
  });

  it("detects the current device timezone from Intl", () => {
    const resolvedOptions = jest.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions");
    resolvedOptions.mockReturnValue({ timeZone: "Australia/Melbourne" } as Intl.ResolvedDateTimeFormatOptions);

    expect(detectDeviceTimezone()).toBe("Australia/Melbourne");

    resolvedOptions.mockRestore();
  });

  it("returns null when the device timezone cannot be detected", () => {
    const resolvedOptions = jest.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions");
    resolvedOptions.mockReturnValue({} as Intl.ResolvedDateTimeFormatOptions);

    expect(detectDeviceTimezone()).toBeNull();

    resolvedOptions.mockRestore();
  });

  it("auto-syncs the detected timezone when it differs from the stored preference", async () => {
    const preferences = {
      accent_preference: "us" as const,
      translation_locale: "zh-Hans" as const,
      knowledge_view_preference: "cards" as const,
      show_translations_by_default: true,
      review_depth_preset: "balanced" as const,
      timezone: "UTC",
      enable_confidence_check: true,
      enable_word_spelling: true,
      enable_audio_spelling: false,
      show_pictures_in_questions: false,
    };

    mockApiClient.put.mockResolvedValueOnce({
      ...preferences,
      timezone: "Australia/Melbourne",
    });

    await syncDetectedDeviceTimezone(preferences, "Australia/Melbourne");

    expect(mockApiClient.put).toHaveBeenCalledWith("/user-preferences", {
      timezone: "Australia/Melbourne",
    });
  });

  it("skips timezone sync when the detected timezone matches the stored preference", async () => {
    const preferences = {
      accent_preference: "us" as const,
      translation_locale: "zh-Hans" as const,
      knowledge_view_preference: "cards" as const,
      show_translations_by_default: true,
      review_depth_preset: "balanced" as const,
      timezone: "Australia/Melbourne",
      enable_confidence_check: true,
      enable_word_spelling: true,
      enable_audio_spelling: false,
      show_pictures_in_questions: false,
    };

    const result = await syncDetectedDeviceTimezone(preferences, "Australia/Melbourne");

    expect(result).toEqual(preferences);
    expect(mockApiClient.put).not.toHaveBeenCalled();
  });
});
