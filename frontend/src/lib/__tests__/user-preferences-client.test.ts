import {
  getUserPreferences,
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
    });

    expect(result).toEqual({ accent_preference: "au" });
    expect(mockApiClient.put).toHaveBeenCalledWith("/user-preferences", {
      accent_preference: "au",
      translation_locale: "es",
      knowledge_view_preference: "list",
    });
  });
});
