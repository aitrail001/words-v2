import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams } from "next/navigation";
import HomePage from "@/app/page";
import WordEntryPage from "@/app/word/[entryId]/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";
import {
  getKnowledgeMapDashboard,
  getKnowledgeMapEntryDetail,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  useParams: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client");

describe("WordEntryPage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockGetKnowledgeMapDashboard = getKnowledgeMapDashboard as jest.MockedFunction<typeof getKnowledgeMapDashboard>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<typeof getKnowledgeMapEntryDetail>;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.MockedFunction<typeof updateKnowledgeEntryStatus>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseParams.mockReturnValue({ entryId: "word-1" } as never);
    mockGetKnowledgeMapDashboard.mockResolvedValue({
      total_entries: 13760,
      counts: {
        undecided: 2385,
        to_learn: 4293,
        learning: 7082,
        known: 0,
      },
      discovery_range_start: 7001,
      discovery_range_end: 7100,
      discovery_entry: {
        entry_type: "word",
        entry_id: "word-1",
        display_text: "Resilience",
        browse_rank: 7002,
        status: "undecided",
      },
      next_learn_entry: {
        entry_type: "word",
        entry_id: "word-2",
        display_text: "Drum",
        browse_rank: 2616,
        status: "to_learn",
      },
    });
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockUpdateKnowledgeEntryStatus.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      status: "known",
    });
  });

  it("renders the standalone word detail route with meaning navigation and translation toggle", async () => {
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
        {
          id: "meaning-2",
          definition: "The side of a river.",
          part_of_speech: "noun",
          examples: [{ id: "example-2", sentence: "They sat on the river bank.", difficulty: "A2" }],
          translations: [{ id: "translation-2", language: "zh-Hans", translation: "河岸" }],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [{ relation_type: "synonym", related_words: ["lender"] }],
      confusable_words: [{ word: "bench", note: "Different object." }],
      previous_entry: null,
      next_entry: null,
    });

    const user = userEvent.setup();
    render(<WordEntryPage />);

    expect(await screen.findByText("Bank")).toBeInTheDocument();
    expect(mockGetKnowledgeMapEntryDetail).toHaveBeenCalledWith("word", "word-1");
    expect(screen.queryByRole("link", { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.getByText(/meaning 1 of 2/i)).toBeInTheDocument();
    expect(screen.getByText("银行")).toBeInTheDocument();
    expect(screen.getByText("Confusing Words")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /translation on/i }));
    expect(screen.queryByText("银行")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: ">" }));
    expect(await screen.findByText("The side of a river.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /known/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("word", "word-1", "known");
      expect(screen.getByText(/status: known/i)).toBeInTheDocument();
    });
  });

  it("shows a real error state when the standalone detail request fails", async () => {
    mockGetKnowledgeMapEntryDetail.mockRejectedValue(new Error("not found"));

    render(<WordEntryPage />);

    expect(await screen.findByText(/unable to load this entry/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to knowledge map/i })).toHaveAttribute("href", "/knowledge-map");
    expect(screen.queryByText(/loading learner detail/i)).not.toBeInTheDocument();
  });

  it("routes the dashboard learn card to the standalone word detail route", async () => {
    render(<HomePage />);

    expect(await screen.findByRole("link", { name: /learn next: drum/i })).toHaveAttribute("href", "/word/word-2");
  });

  it("redirects unauthenticated standalone word detail routes", () => {
    expect(getAuthRedirectPath("/word/word-1", false)).toBe(
      "/login?next=%2Fword%2Fword-1",
    );
  });
});
