import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams } from "next/navigation";
import KnowledgeEntryPage from "@/app/knowledge/[entryType]/[entryId]/page";
import {
  getKnowledgeMapEntryDetail,
  getKnowledgeMapSearchHistory,
  searchKnowledgeMap,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";

jest.mock("next/navigation", () => ({
  useParams: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client");

describe("KnowledgeEntryPage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<typeof getKnowledgeMapEntryDetail>;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.MockedFunction<typeof updateKnowledgeEntryStatus>;
  const mockGetKnowledgeMapSearchHistory = getKnowledgeMapSearchHistory as jest.MockedFunction<typeof getKnowledgeMapSearchHistory>;
  const mockSearchKnowledgeMap = searchKnowledgeMap as jest.MockedFunction<typeof searchKnowledgeMap>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetKnowledgeMapSearchHistory.mockResolvedValue({
      items: [{ query: "bank", entry_type: "word", entry_id: "word-1", last_searched_at: "2026-03-23T00:00:00Z" }],
    });
    mockSearchKnowledgeMap.mockResolvedValue({ items: [] });
    mockUpdateKnowledgeEntryStatus.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      status: "known",
    });
  });

  it("renders word detail and updates status", async () => {
    mockUseParams.mockReturnValue({ entryType: "word", entryId: "word-1" } as any);
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "Bank",
      normalized_form: "bank",
      browse_rank: 20,
      status: "to_learn",
      cefr_level: "A2",
      pronunciation: "/baŋk/",
      translation: "银行",
      primary_definition: "A financial institution.",
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          part_of_speech: "noun",
          examples: [{ id: "example-1", sentence: "I went to the bank.", difficulty: "A1" }],
          translations: [{ id: "translation-1", language: "zh-Hans", translation: "银行" }],
          relations: [],
        },
      ],
      senses: [],
      previous_entry: null,
      next_entry: null,
    });

    const user = userEvent.setup();
    render(<KnowledgeEntryPage />);

    expect(await screen.findByText("Bank")).toBeInTheDocument();
    expect(screen.getByText("/baŋk/")).toBeInTheDocument();
    expect(screen.getAllByText("A financial institution.").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /known/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("word", "word-1", "known");
      expect(screen.getByText(/status: known/i)).toBeInTheDocument();
    });
  });

  it("renders phrase detail and recent search history", async () => {
    mockUseParams.mockReturnValue({ entryType: "phrase", entryId: "phrase-1" } as any);
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "Bank on",
      normalized_form: "bank on",
      browse_rank: 21,
      status: "learning",
      cefr_level: "B1",
      pronunciation: null,
      translation: "依靠",
      primary_definition: "To rely on someone.",
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To rely on someone.",
          part_of_speech: "phrasal verb",
          examples: [{ id: "example-1", sentence: "You can bank on me.", difficulty: "B1" }],
        },
      ],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryPage />);

    expect(await screen.findByText("Bank on")).toBeInTheDocument();
    expect(screen.getAllByText("To rely on someone.").length).toBeGreaterThan(0);
    expect(screen.getByText(/recent searches/i)).toBeInTheDocument();
    expect(screen.getByText("bank")).toBeInTheDocument();
  });
});
