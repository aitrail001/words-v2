import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams, useRouter } from "next/navigation";
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

describe("WordEntryPage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
  const mockGetKnowledgeMapDashboard = getKnowledgeMapDashboard as jest.MockedFunction<typeof getKnowledgeMapDashboard>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<typeof getKnowledgeMapEntryDetail>;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.MockedFunction<typeof updateKnowledgeEntryStatus>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseParams.mockReturnValue({ entryId: "word-1" } as never);
    mockUseRouter.mockReturnValue({ push: jest.fn() } as never);
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
    mockUpdateKnowledgeEntryStatus
      .mockResolvedValueOnce({
        entry_type: "word",
        entry_id: "word-1",
        status: "to_learn",
      })
      .mockResolvedValueOnce({
        entry_type: "word",
        entry_id: "word-1",
        status: "learning",
      })
      .mockResolvedValueOnce({
        entry_type: "word",
        entry_id: "word-1",
        status: "known",
      });
    mockGetKnowledgeMapEntryDetail
      .mockResolvedValueOnce({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "Bank",
      normalized_form: "bank",
      browse_rank: 20,
      status: "undecided",
      cefr_level: "A2",
      pronunciation: "/baŋk/",
      translation: "银行",
      primary_definition: "A financial institution.",
      supported_translation_locales: ["ar", "es", "ja", "pt-BR", "zh-Hans"],
      forms: {
        verb_forms: {
          base: "bank",
          past: "banked",
          gerund: "banking",
          past_participle: "banked",
          third_person_singular: "banks",
        },
        plural_forms: ["banks"],
        derivations: [{ text: "banker", target: { entry_type: "word", entry_id: "word-9", display_text: "banker" } }],
        comparative: "banker",
        superlative: "bankest",
      },
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          localized_definition: "银行",
          part_of_speech: "noun",
          usage_note: "Common in finance.",
          localized_usage_note: "金融中常见。",
          register: "neutral",
          primary_domain: "general",
          secondary_domains: ["finance"],
          grammar_patterns: ["bank account", "go to the bank"],
          synonyms: [{ text: "lender", target: { entry_type: "word", entry_id: "word-2", display_text: "lender" } }],
          antonyms: [],
          collocations: [{ text: "bank account", target: null }],
          examples: [
            {
              id: "example-1",
              sentence: "I went to the bank.",
              difficulty: "A1",
              translation: "我去了银行。",
              linked_entries: [{ text: "bank", entry_type: "word", entry_id: "word-1" }],
            },
          ],
          translations: [{ id: "translation-1", language: "zh-Hans", translation: "银行", usage_note: "金融中常见。", examples: ["我去了银行。"] }],
          relations: [],
        },
        {
          id: "meaning-2",
          definition: "The side of a river.",
          localized_definition: "河岸",
          part_of_speech: "noun",
          usage_note: "Common in geography.",
          localized_usage_note: "地理语境中常见。",
          register: "neutral",
          primary_domain: "general",
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [
            {
              id: "example-2",
              sentence: "They sat on the river bank.",
              difficulty: "A2",
              translation: "他们坐在河岸边。",
              linked_entries: [{ text: "bank", entry_type: "word", entry_id: "word-1" }],
            },
          ],
          translations: [{ id: "translation-2", language: "zh-Hans", translation: "河岸", usage_note: "地理语境中常见。", examples: ["他们坐在河岸边。"] }],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [{ relation_type: "synonym", related_words: ["lender"] }],
      confusable_words: [{ word: "bench", note: "Different object.", target: null }],
      previous_entry: null,
      next_entry: null,
      })
      .mockResolvedValueOnce({
        entry_type: "word",
        entry_id: "word-2",
        display_text: "Lender",
        normalized_form: "lender",
        browse_rank: 25,
        status: "known",
        cefr_level: "B1",
        pronunciation: "/ˈlen.də/",
        translation: "放贷人",
        primary_definition: "A person or organization that lends money.",
        supported_translation_locales: ["ar", "es", "ja", "pt-BR", "zh-Hans"],
        forms: null,
        meanings: [
          {
            id: "meaning-3",
            definition: "A person or organization that lends money.",
            localized_definition: "放贷人",
            part_of_speech: "noun",
            usage_note: null,
            localized_usage_note: null,
            register: "neutral",
            primary_domain: "finance",
            secondary_domains: [],
            grammar_patterns: [],
            synonyms: [],
            antonyms: [],
            collocations: [],
            examples: [
              {
                id: "example-3",
                sentence: "The lender approved the loan.",
                difficulty: "B1",
                translation: "放贷人批准了贷款。",
                linked_entries: [],
              },
            ],
            translations: [
              {
                id: "translation-3",
                language: "zh-Hans",
                translation: "放贷人",
                usage_note: null,
                examples: ["放贷人批准了贷款。"],
              },
            ],
            relations: [],
          },
        ],
        senses: [],
        relation_groups: [],
        confusable_words: [],
        previous_entry: null,
        next_entry: null,
      });

    const user = userEvent.setup();
    render(<WordEntryPage />);

    expect(await screen.findByText("Bank")).toBeInTheDocument();
    expect(mockGetKnowledgeMapEntryDetail).toHaveBeenCalledWith("word", "word-1");
    expect(screen.queryByRole("link", { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.getByText(/meaning 1 of 2/i)).toBeInTheDocument();
    expect(screen.getByText("A financial institution.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chinese \(Simplified\) On/i })).toBeInTheDocument();
    expect(screen.getByText("Confusing Words")).toBeInTheDocument();
    expect(screen.getByText("金融中常见。")).toBeInTheDocument();
    expect(screen.getByText("I went to the")).toBeInTheDocument();
    expect(screen.getByText("Verb Forms")).toBeInTheDocument();
    expect(screen.getByText("Pro Tips")).toBeInTheDocument();
    expect(screen.getByText("Word Variants")).toBeInTheDocument();
    expect(screen.getByText("Comparative")).toBeInTheDocument();
    expect(screen.getAllByText("banker").length).toBeGreaterThan(0);
    expect(screen.getByText("Superlative")).toBeInTheDocument();
    expect(screen.getByText("bankest")).toBeInTheDocument();
    expect(screen.queryByText(/use this link to separate close meanings faster while you review/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /should learn/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /already know/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "lender" }));
    expect(await screen.findByText("Lender")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /look up/i })).toHaveAttribute("href", "/word/word-2");
    expect(screen.getByRole("button", { name: /got it!/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /got it!/i }));
    await waitFor(() => {
      expect(screen.queryByText("Lender")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Chinese \(Simplified\) On/i }));
    expect(screen.queryByText("银行")).not.toBeInTheDocument();
    expect(screen.queryByText("我去了银行。")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: ">" }));
    expect(await screen.findByText("The side of a river.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /should learn/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("word", "word-1", "to_learn");
      expect(screen.getByRole("button", { name: /learn now/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /learn now/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("word", "word-1", "learning");
      expect(screen.getByText(/status: learning/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /known/i }));

    await waitFor(() => {
      expect(mockUpdateKnowledgeEntryStatus).toHaveBeenCalledWith("word", "word-1", "known");
      expect(screen.getByText(/status: known/i)).toBeInTheDocument();
    });
  });

  it("shows a real error state when the standalone detail request fails", async () => {
    mockGetKnowledgeMapEntryDetail.mockReset();
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
