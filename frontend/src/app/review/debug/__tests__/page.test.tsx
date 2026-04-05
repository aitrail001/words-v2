import { render, screen, waitFor } from "@testing-library/react";
import ReviewDebugPage from "@/app/review/debug/page";
import { apiClient } from "@/lib/api-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    get: jest.fn(),
  },
}));

describe("ReviewDebugPage", () => {
  const mockGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the due queue prompt families for the signed-in user", async () => {
    mockGet.mockResolvedValue([
      {
        id: "queue-1",
        word: "persistence",
        definition: "The ability to keep going despite difficulties.",
        prompt: { prompt_type: "sentence_gap", question: "Fill the gap." },
        detail: { entry_type: "word", entry_id: "word-1", display_text: "persistence", meaning_count: 1, compare_with: [], meanings: [] },
      },
      {
        id: "queue-2",
        word: "tranquil",
        definition: "Calm and peaceful.",
        prompt: { prompt_type: "audio_to_definition", question: "Listen and choose." },
        detail: { entry_type: "word", entry_id: "word-2", display_text: "tranquil", meaning_count: 1, compare_with: [], meanings: [] },
      },
    ] as never);

    render(<ReviewDebugPage />);

    expect(await screen.findByRole("heading", { name: /current queue prompt types/i })).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/reviews/queue/due"));
    expect(screen.getByText(/1. sentence gap/i)).toBeInTheDocument();
    expect(screen.getByText(/2. audio to definition/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })[0]).toHaveAttribute("href", "/review?queue_item_id=queue-1");
  });

  it("shows an empty state when there are no due items", async () => {
    mockGet.mockResolvedValue([] as never);

    render(<ReviewDebugPage />);

    expect(await screen.findByText(/no due review items/i)).toBeInTheDocument();
  });
});
