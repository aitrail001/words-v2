import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconVoiceRunsPage from "@/app/lexicon/voice-runs/page";
import { useRouter } from "next/navigation";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { getLexiconVoiceRunDetail, getLexiconVoiceRuns } from "@/lib/lexicon-ops-client";

jest.mock("next/navigation", () => ({ useRouter: jest.fn() }));
jest.mock("@/lib/auth-session", () => ({ readAccessToken: jest.fn() }));
jest.mock("@/lib/auth-redirect", () => ({ redirectToLogin: jest.fn() }));
jest.mock("@/lib/lexicon-ops-client", () => ({
  getLexiconVoiceRunDetail: jest.fn(),
  getLexiconVoiceRuns: jest.fn(),
}));

describe("LexiconVoiceRunsPage", () => {
  const mockUseRouter = useRouter as jest.Mock;
  const mockReadAccessToken = readAccessToken as jest.Mock;
  const mockRedirectToLogin = redirectToLogin as jest.Mock;
  const mockGetLexiconVoiceRunDetail = getLexiconVoiceRunDetail as jest.Mock;
  const mockGetLexiconVoiceRuns = getLexiconVoiceRuns as jest.Mock;
  const fetchMock = jest.fn();
  const push = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = fetchMock as unknown as typeof fetch;
    fetchMock.mockResolvedValue({
      ok: true,
      text: async () => "{\"status\":\"generated\"}\n",
    });
    URL.createObjectURL = jest.fn(() => "blob:test");
    URL.revokeObjectURL = jest.fn();
    mockUseRouter.mockReturnValue({ push, replace: jest.fn() });
    mockReadAccessToken.mockReturnValue("active-token");
    mockGetLexiconVoiceRunDetail.mockResolvedValue({
      run_name: "voice-roundtrip",
      run_path: "/data/lexicon/voice/voice-roundtrip",
      updated_at: "2026-03-29T10:00:00Z",
      planned_count: 6,
      generated_count: 4,
      existing_count: 1,
      failed_count: 1,
      locale_counts: { "en-US": 5, "en-GB": 1 },
      voice_role_counts: { female: 3, male: 3 },
      content_scope_counts: { word: 2, definition: 2, example: 2 },
      source_references: ["voice-roundtrip"],
      artifacts: {
        voice_plan_url: "/api/lexicon-ops/voice-runs/voice-roundtrip/artifacts/voice_plan.jsonl",
        voice_manifest_url: "/api/lexicon-ops/voice-runs/voice-roundtrip/artifacts/voice_manifest.jsonl",
        voice_errors_url: "/api/lexicon-ops/voice-runs/voice-roundtrip/artifacts/voice_errors.jsonl",
      },
      latest_manifest_rows: [{ status: "generated", locale: "en-US" }],
      latest_error_rows: [{ status: "failed", generation_error: "boom" }],
    });
    mockGetLexiconVoiceRuns.mockResolvedValue([
      {
        run_name: "voice-roundtrip",
        run_path: "/data/lexicon/voice/voice-roundtrip",
        updated_at: "2026-03-29T10:00:00Z",
        planned_count: 6,
        generated_count: 4,
        existing_count: 1,
        failed_count: 1,
      },
      {
        run_name: "voice-run-b",
        run_path: "/data/lexicon/voice/voice-run-b",
        updated_at: "2026-03-29T09:00:00Z",
        planned_count: 4,
        generated_count: 4,
        existing_count: 0,
        failed_count: 0,
      },
      {
        run_name: "voice-run-c",
        run_path: "/data/lexicon/voice/voice-run-c",
        updated_at: "2026-03-29T08:00:00Z",
        planned_count: 3,
        generated_count: 3,
        existing_count: 0,
        failed_count: 0,
      },
      {
        run_name: "voice-run-d",
        run_path: "/data/lexicon/voice/voice-run-d",
        updated_at: "2026-03-29T07:00:00Z",
        planned_count: 2,
        generated_count: 2,
        existing_count: 0,
        failed_count: 0,
      },
    ]);
    window.history.pushState({}, "", "/lexicon/voice-runs");
  });

  it("redirects unauthenticated users to login", async () => {
    mockReadAccessToken.mockReturnValue(null);
    render(<LexiconVoiceRunsPage />);
    await waitFor(() => expect(mockRedirectToLogin).toHaveBeenCalledWith("/lexicon/voice-runs"));
  });

  it("shows voice runs separately and supports detail/import actions", async () => {
    const user = userEvent.setup();
    render(<LexiconVoiceRunsPage />);

    expect(screen.getByTestId("lexicon-voice-section-nav")).toHaveTextContent("Storage");
    expect(screen.getByTestId("lexicon-voice-section-nav")).toHaveTextContent("Voice Runs");
    expect(screen.getByTestId("lexicon-voice-section-nav")).toHaveTextContent("Voice DB Import");
    expect(screen.getByTestId("lexicon-voice-runs")).toHaveTextContent("Loading voice runs");
    await waitFor(() => expect(mockGetLexiconVoiceRuns).toHaveBeenCalled());
    expect(screen.getByTestId("lexicon-voice-runs")).toHaveTextContent("voice-roundtrip");
    expect(screen.getByTestId("lexicon-voice-runs")).toHaveTextContent("planned: 6");
    await user.click(screen.getByTestId("lexicon-voice-run-voice-roundtrip"));
    await waitFor(() => expect(mockGetLexiconVoiceRunDetail).toHaveBeenCalledWith("voice-roundtrip"));
    expect(screen.getByTestId("lexicon-voice-run-detail")).toHaveTextContent("Latest manifest rows");
    expect(screen.getByTestId("lexicon-voice-run-detail")).toHaveTextContent("Locale counts");
    expect(screen.getByTestId("lexicon-voice-run-detail")).toHaveTextContent("en-US");
    expect(screen.getByTestId("lexicon-voice-run-detail")).toHaveTextContent("voice_plan.jsonl");
    expect(screen.getByTestId("lexicon-voice-run-detail")).toHaveTextContent("boom");
  });

  it("downloads run artifacts with authenticated fetch", async () => {
    const user = userEvent.setup();
    render(<LexiconVoiceRunsPage />);

    await waitFor(() => expect(mockGetLexiconVoiceRunDetail).toHaveBeenCalledWith("voice-roundtrip"));
    await user.click(screen.getByTestId("lexicon-voice-artifact-voice_manifest.jsonl"));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/lexicon-ops/voice-runs/voice-roundtrip/artifacts/voice_manifest.jsonl",
        { headers: { Authorization: "Bearer active-token" } },
      ),
    );
  });

  it("pages recent voice runs horizontally", async () => {
    const user = userEvent.setup();
    render(<LexiconVoiceRunsPage />);

    await waitFor(() => expect(mockGetLexiconVoiceRuns).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("lexicon-voice-runs")).toHaveTextContent("voice-roundtrip"));
    expect(screen.getByTestId("lexicon-voice-run-pagination")).toHaveTextContent("Page 1 of 2");
    expect(screen.getByTestId("lexicon-voice-run-page")).toHaveTextContent("voice-roundtrip");
    expect(screen.getByTestId("lexicon-voice-run-page")).toHaveTextContent("voice-run-b");
    expect(screen.getByTestId("lexicon-voice-run-page")).not.toHaveTextContent("voice-run-c");
    expect(screen.getByTestId("lexicon-voice-run-page")).not.toHaveTextContent("voice-run-d");

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByTestId("lexicon-voice-run-pagination")).toHaveTextContent("Page 2 of 2");
    expect(screen.getByTestId("lexicon-voice-run-page")).toHaveTextContent("voice-run-c");
    expect(screen.getByTestId("lexicon-voice-run-page")).toHaveTextContent("voice-run-d");
    expect(screen.getByTestId("lexicon-voice-run-page")).not.toHaveTextContent("voice-run-b");
  });

  it("opens voice import from recent runs and run detail", async () => {
    const user = userEvent.setup();
    render(<LexiconVoiceRunsPage />);

    await waitFor(() => expect(mockGetLexiconVoiceRuns).toHaveBeenCalled());
    await user.click(screen.getByTestId("lexicon-voice-run-import-voice-roundtrip"));
    expect(push).toHaveBeenCalledWith("/lexicon/voice-import?inputPath=%2Fdata%2Flexicon%2Fvoice%2Fvoice-roundtrip%2Fvoice_manifest.jsonl&language=en");

    await user.click(screen.getByTestId("lexicon-voice-run-voice-roundtrip"));
    await waitFor(() => expect(mockGetLexiconVoiceRunDetail).toHaveBeenCalledWith("voice-roundtrip"));
    await user.click(screen.getByTestId("lexicon-voice-run-detail-import"));
    expect(push).toHaveBeenLastCalledWith("/lexicon/voice-import?inputPath=%2Fdata%2Flexicon%2Fvoice%2Fvoice-roundtrip%2Fvoice_manifest.jsonl&language=en");
  });
});
