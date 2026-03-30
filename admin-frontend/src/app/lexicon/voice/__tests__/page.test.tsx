import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LexiconVoicePage from "@/app/lexicon/voice-storage/page";
import { useRouter } from "next/navigation";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { getLexiconVoiceStoragePolicies, rewriteLexiconVoiceStorage } from "@/lib/lexicon-ops-client";

jest.mock("next/navigation", () => ({ useRouter: jest.fn() }));
jest.mock("@/lib/auth-session", () => ({ readAccessToken: jest.fn() }));
jest.mock("@/lib/auth-redirect", () => ({ redirectToLogin: jest.fn() }));
jest.mock("@/lib/lexicon-ops-client", () => ({
  getLexiconVoiceStoragePolicies: jest.fn(),
  rewriteLexiconVoiceStorage: jest.fn(),
}));

describe("LexiconVoicePage", () => {
  const mockUseRouter = useRouter as jest.Mock;
  const mockReadAccessToken = readAccessToken as jest.Mock;
  const mockRedirectToLogin = redirectToLogin as jest.Mock;
  const mockGetLexiconVoiceStoragePolicies = getLexiconVoiceStoragePolicies as jest.Mock;
  const mockRewriteLexiconVoiceStorage = rewriteLexiconVoiceStorage as jest.Mock;
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
    mockGetLexiconVoiceStoragePolicies.mockResolvedValue([
      {
        id: "policy-1",
        policy_key: "word_default",
        content_scope: "word",
        primary_storage_kind: "local",
        primary_storage_base: "/tmp/voice-a",
        fallback_storage_kind: "http",
        fallback_storage_base: "https://backup.example.com/voice",
        asset_count: 2,
      },
    ]);
    mockRewriteLexiconVoiceStorage.mockResolvedValue({
      matched_count: 3,
      updated_count: 0,
      dry_run: true,
      storage_kind: "s3",
      storage_base: "https://cdn.example.com/voice",
      fallback_storage_kind: "http",
      fallback_storage_base: "https://backup.example.com/voice",
    });
    window.history.pushState({}, "", "/lexicon/voice-storage");
  });

  it("redirects unauthenticated users to login", async () => {
    mockReadAccessToken.mockReturnValue(null);
    render(<LexiconVoicePage />);
    await waitFor(() => expect(mockRedirectToLogin).toHaveBeenCalledWith("/lexicon/voice-storage"));
  });

  it("loads DB policies even without a source reference filter", async () => {
    const user = userEvent.setup();
    render(<LexiconVoicePage />);

    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("Loading storage policies");
    await waitFor(() => expect(mockGetLexiconVoiceStoragePolicies).toHaveBeenCalledWith(undefined));
    expect(screen.getByTestId("lexicon-voice-section-nav")).toHaveTextContent("Storage");
    expect(screen.getByTestId("lexicon-voice-section-nav")).toHaveTextContent("Voice Runs");
    expect(screen.getByTestId("lexicon-voice-section-nav")).toHaveTextContent("Voice DB Import");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("These are the live DB storage policies used by voice assets");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("Voice import updates asset relative paths and voice metadata only");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("word_default");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("local");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("fallback-enabled");
    expect(screen.queryByTestId("lexicon-voice-panel")).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /word_default/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit policy" }));
    expect(screen.getByTestId("lexicon-voice-panel")).toHaveTextContent("word_default");
  });

  it("supports policy-specific dry-run rewrite on the storage page", async () => {
    const user = userEvent.setup();
    render(<LexiconVoicePage />);

    await waitFor(() => expect(mockGetLexiconVoiceStoragePolicies).toHaveBeenCalledWith(undefined));
    await user.click(screen.getByRole("button", { name: "Edit policy" }));
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("word_default");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("primary: local | /tmp/voice-a");
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("fallback: http | https://backup.example.com/voice");
    expect(screen.getByTestId("lexicon-voice-panel")).toHaveTextContent("Editing policy word_default · Scope: word");
    expect(screen.getByTestId("lexicon-voice-panel")).toHaveTextContent("Voice import updates asset relative paths; policy roots set how those paths resolve at runtime.");
    expect(screen.getByTestId("lexicon-voice-storage-base")).toHaveValue("/tmp/voice-a");
    await user.selectOptions(screen.getByTestId("lexicon-voice-storage-kind"), "s3");
    await user.clear(screen.getByTestId("lexicon-voice-storage-base"));
    await user.type(screen.getByTestId("lexicon-voice-storage-base"), "https://cdn.example.com/voice");
    await user.selectOptions(screen.getByTestId("lexicon-voice-fallback-storage-kind"), "http");
    await user.clear(screen.getByTestId("lexicon-voice-fallback-storage-base"));
    await user.type(screen.getByTestId("lexicon-voice-fallback-storage-base"), "https://backup.example.com/voice");
    await user.click(screen.getByTestId("lexicon-voice-dry-run-button"));

    await waitFor(() =>
      expect(mockRewriteLexiconVoiceStorage).toHaveBeenCalledWith({
        policy_ids: ["policy-1"],
        storage_kind: "s3",
        storage_base: "https://cdn.example.com/voice",
        fallback_storage_kind: "http",
        fallback_storage_base: "https://backup.example.com/voice",
        dry_run: true,
      }),
    );
    expect(screen.getByTestId("lexicon-voice-result")).toHaveTextContent("Matched assets");
    expect(screen.getByTestId("lexicon-voice-result")).toHaveTextContent("3");
    expect(screen.getByTestId("lexicon-voice-result")).toHaveTextContent("Fallback");
    expect(screen.getByTestId("lexicon-voice-result")).toHaveTextContent("http | https://backup.example.com/voice");
  });

  it("refreshes the current DB storage policies after apply", async () => {
    const user = userEvent.setup();
    mockGetLexiconVoiceStoragePolicies
      .mockResolvedValueOnce([
        {
          id: "policy-1",
          policy_key: "word_default",
          content_scope: "word",
          primary_storage_kind: "local",
          primary_storage_base: "/tmp/voice-a",
          fallback_storage_kind: "http",
          fallback_storage_base: "https://backup.example.com/voice",
          asset_count: 2,
        },
      ])
      .mockResolvedValueOnce([
        {
          id: "policy-1",
          policy_key: "word_default",
          content_scope: "word",
          primary_storage_kind: "s3",
          primary_storage_base: "https://cdn.example.com/voice",
          fallback_storage_kind: "http",
          fallback_storage_base: "https://backup.example.com/voice",
          asset_count: 2,
        },
      ]);
    mockRewriteLexiconVoiceStorage.mockResolvedValueOnce({
      matched_count: 3,
      updated_count: 3,
      dry_run: false,
      storage_kind: "s3",
      storage_base: "https://cdn.example.com/voice",
      fallback_storage_kind: "http",
      fallback_storage_base: "https://backup.example.com/voice",
    });

    render(<LexiconVoicePage />);

    await waitFor(() => expect(mockGetLexiconVoiceStoragePolicies).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Edit policy" }));
    await user.selectOptions(screen.getByTestId("lexicon-voice-storage-kind"), "s3");
    await user.clear(screen.getByTestId("lexicon-voice-storage-base"));
    await user.type(screen.getByTestId("lexicon-voice-storage-base"), "https://cdn.example.com/voice");
    await user.click(screen.getByTestId("lexicon-voice-apply-button"));

    await waitFor(() => expect(mockRewriteLexiconVoiceStorage).toHaveBeenCalledWith({
      policy_ids: ["policy-1"],
      storage_kind: "s3",
      storage_base: "https://cdn.example.com/voice",
      fallback_storage_kind: "http",
      fallback_storage_base: "https://backup.example.com/voice",
      dry_run: false,
    }));
    await waitFor(() => expect(mockGetLexiconVoiceStoragePolicies).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("lexicon-voice-current-policies")).toHaveTextContent("primary: s3 | https://cdn.example.com/voice");
  });

});
