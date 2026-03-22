import { apiClient, ApiError } from "../api-client";
import { redirectToLogin } from "../auth-redirect";

jest.mock("../auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

type MockResponseInit = {
  status: number;
  body?: unknown;
};

const createMockResponse = ({ status, body }: MockResponseInit): Response =>
  ({
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body ?? null),
  }) as unknown as Response;

describe("apiClient auth lifecycle", () => {
  const mockFetch = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockReset();
    (global.fetch as unknown) = mockFetch;
    window.localStorage.clear();
    apiClient.setTokens(null, null);
  });

  it("attaches Authorization header using persisted token", async () => {
    apiClient.setTokens("seed-token", "seed-refresh");
    mockFetch.mockResolvedValueOnce(
      createMockResponse({
        status: 200,
        body: [{ id: "1", word: "bank" }],
      }),
    );

    await apiClient.get("/words/search?q=bank");

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/words/search?q=bank",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer seed-token",
        }),
      }),
    );
  });

  it("refreshes once on 401 and retries the original request", async () => {
    apiClient.setTokens("expired-token", "refresh-token");
    mockFetch
      .mockResolvedValueOnce(
        createMockResponse({
          status: 401,
          body: { detail: "expired" },
        }),
      )
      .mockResolvedValueOnce(
        createMockResponse({
          status: 200,
          body: { access_token: "fresh-token", refresh_token: "next-refresh" },
        }),
      )
      .mockResolvedValueOnce(
        createMockResponse({
          status: 200,
          body: [{ id: "2", word: "branch" }],
        }),
      );

    const result = await apiClient.get<Array<{ id: string; word: string }>>(
      "/words/search?q=br",
    );

    expect(result).toEqual([{ id: "2", word: "branch" }]);
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(mockFetch.mock.calls[1][0]).toBe("/api/auth/refresh");
    expect(mockFetch.mock.calls[1][1]).toEqual(
      expect.objectContaining({
        body: JSON.stringify({ refresh_token: "refresh-token" }),
        method: "POST",
      }),
    );
    expect(mockFetch.mock.calls[2][1]).toEqual(
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer fresh-token",
        }),
      }),
    );
    expect(window.localStorage.getItem("words_refresh_token")).toBe("next-refresh");
  });

  it("clears token and redirects to login when refresh fails", async () => {
    apiClient.setTokens("expired-token", "expired-refresh");
    mockFetch
      .mockResolvedValueOnce(
        createMockResponse({
          status: 401,
          body: { detail: "expired" },
        }),
      )
      .mockResolvedValueOnce(
        createMockResponse({
          status: 401,
          body: { detail: "refresh failed" },
        }),
      );

    await expect(apiClient.get("/reviews/queue/due")).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(window.localStorage.getItem("words_access_token")).toBeNull();
    expect(window.localStorage.getItem("words_refresh_token")).toBeNull();
    expect(redirectToLogin).toHaveBeenCalledTimes(1);
  });
});
