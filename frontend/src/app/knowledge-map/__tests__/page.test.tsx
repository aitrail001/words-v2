import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import KnowledgeMapPage from "@/app/knowledge-map/page";
import {
  getKnowledgeMapEntryDetail,
  getKnowledgeMapOverview,
  getKnowledgeMapRange,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client");

describe("KnowledgeMapPage", () => {
  const mockGetKnowledgeMapOverview = getKnowledgeMapOverview as jest.MockedFunction<typeof getKnowledgeMapOverview>;
  const mockGetKnowledgeMapRange = getKnowledgeMapRange as jest.MockedFunction<typeof getKnowledgeMapRange>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<typeof getKnowledgeMapEntryDetail>;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.MockedFunction<typeof updateKnowledgeEntryStatus>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockGetKnowledgeMapOverview.mockResolvedValue({
      bucket_size: 100,
      total_entries: 2,
      ranges: [
        {
          range_start: 1,
          range_end: 100,
          total_entries: 2,
          counts: { undecided: 1, to_learn: 1, learning: 0, known: 0 },
        },
      ],
    });
    mockGetKnowledgeMapRange.mockResolvedValue({
      range_start: 1,
      range_end: 100,
      previous_range_start: null,
      next_range_start: null,
      items: [
        {
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
          part_of_speech: "noun",
          phrase_kind: null,
        },
        {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "Bank on",
          normalized_form: "bank on",
          browse_rank: 21,
          status: "undecided",
          cefr_level: "B1",
          pronunciation: null,
          translation: "依靠",
          primary_definition: "To rely on someone.",
          part_of_speech: null,
          phrase_kind: "phrasal_verb",
        },
      ],
    });
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
      meanings: [],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });
    mockUpdateKnowledgeEntryStatus.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      status: "known",
    });
  });

  it("renders the overview and initial range cards", async () => {
    render(<KnowledgeMapPage />);

    expect(await screen.findByText(/full knowledge map/i)).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-map-mobile-shell")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-map-tile-grid")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /1-100/i })).toBeInTheDocument();
    expect(await screen.findByText("Bank")).toBeInTheDocument();
    expect(screen.getByText("A financial institution.")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-range-strip")).toBeInTheDocument();
    expect(screen.queryByText(/search the graph/i)).not.toBeInTheDocument();
  });

  it("switches between cards, tags, and list views", async () => {
    const user = userEvent.setup();
    render(<KnowledgeMapPage />);

    await screen.findByText("Bank");
    expect(screen.getByTestId("knowledge-card-view")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /tags view/i }));
    expect(screen.getByTestId("knowledge-tags-view")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /list view/i }));
    expect(screen.getByTestId("knowledge-list-view")).toBeInTheDocument();
  });

  it("updates learner status from the cards view", async () => {
    const user = userEvent.setup();
    render(<KnowledgeMapPage />);

    await screen.findByText("Bank");
    await user.click(screen.getByRole("button", { name: /known/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("word", "word-1", "known");
      expect(screen.getByText(/status: known/i)).toBeInTheDocument();
    });
  });
});
