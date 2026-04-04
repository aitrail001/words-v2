import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams, useRouter } from "next/navigation";
import KnowledgeListPage from "@/app/knowledge-list/[status]/page";
import KnowledgeMapPage from "@/app/knowledge-map/page";
import KnowledgeMapRangePage from "@/app/knowledge-map/range/[start]/page";
import PhraseEntryPage from "@/app/phrase/[entryId]/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";
import {
  getKnowledgeMapEntryDetail,
  getKnowledgeMapList,
  getKnowledgeMapOverview,
  getKnowledgeMapRange,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  useParams: jest.fn(),
  useRouter: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client", () => {
  const actual = jest.requireActual("@/lib/user-preferences-client");
  return {
    ...actual,
    getUserPreferences: jest.fn(),
  };
});

describe("PhraseEntryPage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<typeof getKnowledgeMapEntryDetail>;
  const mockGetKnowledgeMapList = getKnowledgeMapList as jest.MockedFunction<typeof getKnowledgeMapList>;
  const mockGetKnowledgeMapOverview = getKnowledgeMapOverview as jest.MockedFunction<typeof getKnowledgeMapOverview>;
  const mockGetKnowledgeMapRange = getKnowledgeMapRange as jest.MockedFunction<typeof getKnowledgeMapRange>;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.MockedFunction<typeof updateKnowledgeEntryStatus>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(window, "confirm").mockReturnValue(true);
    mockUseParams.mockReturnValue({ entryId: "phrase-1" } as never);
    mockUseRouter.mockReturnValue({ push: jest.fn() } as never);
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
    mockGetKnowledgeMapList.mockResolvedValue({
      items: [
        {
          entry_type: "word",
          entry_id: "word-1",
          display_text: "The",
          normalized_form: "the",
          browse_rank: 1,
          status: "known",
          cefr_level: "A1",
          pronunciation: "/ðə/",
          translation: "这",
          primary_definition: "Used before nouns.",
          part_of_speech: "article",
          phrase_kind: null,
        },
      ],
    });
    mockUpdateKnowledgeEntryStatus.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      status: "learning",
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders the standalone phrase detail route without embedded search", async () => {
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
      supported_translation_locales: ["ar", "es", "ja", "pt-BR", "zh-Hans"],
      forms: null,
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To rely on someone.",
          localized_definition: "依靠",
          part_of_speech: "phrasal verb",
          usage_note: "Common spoken phrase.",
          localized_usage_note: "口语中常见。",
          register: "neutral",
          primary_domain: "general",
          secondary_domains: ["relationships"],
          grammar_patterns: ["bank on + noun"],
          synonyms: [{ text: "depend on", target: { entry_type: "phrase", entry_id: "phrase-9", display_text: "depend on" } }],
          antonyms: [],
          collocations: [{ text: "bank on support", target: null }],
          examples: [
            {
              id: "example-1",
              sentence: "You can bank on support from me.",
              difficulty: "B1",
              translation: "你可以指望我的支持。",
              linked_entries: [{ text: "support", entry_type: "word", entry_id: "word-7" }],
            },
          ],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    const user = userEvent.setup();
    render(<PhraseEntryPage />);

    expect(await screen.findByText("Bank on")).toBeInTheDocument();
    expect(mockGetKnowledgeMapEntryDetail).toHaveBeenCalledWith("phrase", "phrase-1");
    expect(screen.queryByPlaceholderText(/search your knowledge map/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Pronunciation unavailable")).not.toBeInTheDocument();
    expect(screen.getByText("口语中常见。")).toBeInTheDocument();
    expect(screen.getByText("You can bank on")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "depend on" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /already knew/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("phrase", "phrase-1", "known");
    });
  });

  it("routes knowledge-map entry links to standalone word and phrase detail routes", async () => {
    const user = userEvent.setup();
    render(<KnowledgeMapPage />);

    expect(await screen.findByRole("link", { name: "1-100", exact: true })).toHaveAttribute(
      "href",
      "/knowledge-map/range/1",
    );

    mockUseParams.mockReturnValue({ start: "1" } as never);
    render(<KnowledgeMapRangePage />);

    expect(await screen.findByRole("link", { name: /learn more/i })).toHaveAttribute("href", "/word/word-1");

    await user.click(screen.getByRole("button", { name: /tags view/i }));
    expect(screen.getByRole("link", { name: "Bank on" })).toHaveAttribute("href", "/phrase/phrase-1");
  });

  it("routes knowledge-list entry links to the standalone detail routes", async () => {
    mockUseParams.mockReturnValue({ status: "known" } as never);

    render(<KnowledgeListPage />);

    expect(await screen.findByRole("link", { name: /the/i })).toHaveAttribute("href", "/word/word-1");
  });

  it("redirects unauthenticated standalone phrase detail routes", () => {
    expect(getAuthRedirectPath("/phrase/phrase-1", false)).toBe(
      "/login?next=%2Fphrase%2Fphrase-1",
    );
  });
});
