import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import { KnowledgeEntryDetailPage } from "@/components/knowledge-entry-detail-page";
import { apiClient } from "@/lib/api-client";
import { getKnowledgeMapEntryDetail } from "@/lib/knowledge-map-client";
import { playLearnerEntryAudio } from "@/lib/learner-audio";
import { getUserPreferences, updateUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client", () => {
  const actual = jest.requireActual("@/lib/knowledge-map-client");

  return {
    ...actual,
    getKnowledgeMapEntryDetail: jest.fn(),
    normalizeLearnerTranslation: jest.fn(actual.normalizeLearnerTranslation),
  };
});
jest.mock("@/lib/api-client", () => {
  const actual = jest.requireActual("@/lib/api-client");
  return {
    ...actual,
    apiClient: {
      post: jest.fn(),
      put: jest.fn(),
    },
  };
});
jest.mock("@/lib/learner-audio", () => ({
  getPlayableLearnerAccents: jest.fn((voiceAssets) => {
    const locales = new Set(
      (voiceAssets ?? []).map((asset: { locale?: string }) => asset.locale?.toLowerCase().replace(/-/g, "_")),
    );
    const accents: Array<"us" | "uk" | "au"> = [];
    if (locales.has("en_us")) {
      accents.push("us");
    }
    if (locales.has("en_gb")) {
      accents.push("uk");
    }
    if (locales.has("en_au")) {
      accents.push("au");
    }
    return accents;
  }),
  getEntryLevelVoiceAssets: jest.fn((voiceAssets) =>
    (voiceAssets ?? []).filter((asset: { content_scope?: string }) => asset.content_scope === "word"),
  ),
  playLearnerEntryAudio: jest.fn(),
  resolveDisplayedPronunciation: jest.fn(
    (
      pronunciation: string | null | undefined,
      pronunciations: Partial<Record<"us" | "uk" | "au", string>> | undefined,
      accent: "us" | "uk" | "au",
    ) => pronunciations?.[accent] ?? pronunciations?.[accent === "us" ? "uk" : "us"] ?? pronunciations?.au ?? pronunciation ?? null,
  ),
  resolveLearnerVoiceAsset: jest.fn((voiceAssets, accent, filters = {}) => {
    const filtered = (voiceAssets ?? []).filter((asset: {
      content_scope?: string;
      meaning_id?: string | null;
      meaning_example_id?: string | null;
      phrase_sense_id?: string | null;
      phrase_sense_example_id?: string | null;
      locale?: string;
    }) => {
      if (filters.contentScope && asset.content_scope !== filters.contentScope) {
        return false;
      }
      if (filters.meaningId !== undefined && (asset.meaning_id ?? null) !== filters.meaningId) {
        return false;
      }
      if (
        filters.meaningExampleId !== undefined
        && (asset.meaning_example_id ?? null) !== filters.meaningExampleId
      ) {
        return false;
      }
      if (filters.phraseSenseId !== undefined && (asset.phrase_sense_id ?? null) !== filters.phraseSenseId) {
        return false;
      }
      if (
        filters.phraseSenseExampleId !== undefined
        && (asset.phrase_sense_example_id ?? null) !== filters.phraseSenseExampleId
      ) {
        return false;
      }
      return true;
    });

    const exactLocale = accent === "us" ? "en_us" : accent === "uk" ? "en_gb" : "en_au";
    return (
      filtered.find((asset: { locale?: string }) => asset.locale?.toLowerCase().replace(/-/g, "_") === exactLocale)
      ?? filtered[0]
      ?? null
    );
  }),
}));
jest.mock("@/lib/user-preferences-client");

const reviewTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatReviewTime(value: string): string {
  return reviewTimeFormatter.format(new Date(value));
}

describe("KnowledgeEntryDetailPage", () => {
  const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<
    typeof getKnowledgeMapEntryDetail
  >;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockUpdateUserPreferences = updateUserPreferences as jest.MockedFunction<typeof updateUserPreferences>;
  const mockPlayLearnerEntryAudio = playLearnerEntryAudio as jest.MockedFunction<typeof playLearnerEntryAudio>;
  const mockPost = apiClient.post as jest.MockedFunction<typeof apiClient.post>;
  const mockPut = apiClient.put as jest.MockedFunction<typeof apiClient.put>;
  const mockNormalizeLearnerTranslation = jest.requireMock("@/lib/knowledge-map-client")
    .normalizeLearnerTranslation as jest.MockedFunction<
    typeof import("@/lib/knowledge-map-client").normalizeLearnerTranslation
  >;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date("2026-04-03T12:00:00Z"));
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({ push: jest.fn() } as never);
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockUpdateUserPreferences.mockResolvedValue({
      accent_preference: "us",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockPlayLearnerEntryAudio.mockResolvedValue(true);
    mockPost.mockReset();
    mockPut.mockReset();
    jest.spyOn(window, "confirm").mockReturnValue(true);
    window.sessionStorage.clear();
    window.history.pushState({}, "", "/word/word-1");
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders both English and localized text for a word detail", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "Bank",
      normalized_form: "bank",
      browse_rank: 20,
      status: "to_learn",
      cefr_level: "A2",
      pronunciation: "/baŋk/",
      pronunciations: { us: "/bæŋk/", uk: "/baŋk/" },
      translation: "银行",
      primary_definition: "A financial institution.",
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          localized_definition: "银行",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [
            { id: "translation-1", language: "zh-Hans", translation: "银行" },
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

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByText("A financial institution.")).toBeInTheDocument();
    expect(await screen.findByText("银行", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("renders both English and localized text for a phrase detail", async () => {
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
          localized_definition: "依靠",
          part_of_speech: "phrasal verb",
          usage_note: "Common spoken phrase.",
          localized_usage_note: "口语中常见。",
          register: "neutral",
          primary_domain: "general",
          secondary_domains: ["relationships"],
          grammar_patterns: ["bank on + noun"],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText("To rely on someone.")).toBeInTheDocument();
    expect(await screen.findByText("依靠", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("hides placeholder translations instead of rendering them as learner data", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "Bank on",
      normalized_form: "bank on",
      browse_rank: 21,
      status: "learning",
      cefr_level: "B1",
      pronunciation: null,
      translation: "Translation unavailable",
      primary_definition: "To rely on someone.",
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To rely on someone.",
          localized_definition: null,
          part_of_speech: "phrasal verb",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText("To rely on someone.")).toBeInTheDocument();
    expect(screen.queryByText("Translation unavailable")).not.toBeInTheDocument();
  });

  it("does not recompute the main detail translation when opening an overlay", async () => {
    mockGetKnowledgeMapEntryDetail.mockImplementation(async (entryType, entryId) => {
      if (entryType === "phrase" && entryId === "phrase-1") {
        return {
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
              localized_definition: "依靠",
              part_of_speech: "phrasal verb",
              usage_note: "Common spoken phrase.",
              localized_usage_note: "口语中常见。",
              register: "neutral",
              primary_domain: "general",
              secondary_domains: ["relationships"],
              grammar_patterns: ["bank on + noun"],
              synonyms: [
                {
                  text: "support on",
                  target: {
                    entry_type: "word",
                    entry_id: "word-2",
                    display_text: "support on",
                  },
                },
              ],
              antonyms: [],
              collocations: [],
              examples: [],
            },
          ],
          relation_groups: [],
          confusable_words: [],
          previous_entry: null,
          next_entry: null,
        };
      }

      return {
        entry_type: "word",
        entry_id: "word-2",
        display_text: "support on",
        normalized_form: "support on",
        browse_rank: 22,
        status: "known",
        cefr_level: null,
        pronunciation: null,
        translation: null,
        primary_definition: "To help sustain something.",
        meanings: [],
        senses: [],
        relation_groups: [],
        confusable_words: [],
        previous_entry: null,
        next_entry: null,
      };
    });

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText("依靠")).toBeInTheDocument();
    const callsBeforeOverlay = mockNormalizeLearnerTranslation.mock.calls.length;
    expect(callsBeforeOverlay).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "support on" }));

    expect(await screen.findByRole("dialog", { name: "support on" })).toBeInTheDocument();
    await waitFor(() =>
      expect(mockNormalizeLearnerTranslation).toHaveBeenCalledTimes(callsBeforeOverlay + 1),
    );
  });

  it("renders two ordered examples for a word meaning when both exist", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "Bank",
      normalized_form: "bank",
      browse_rank: 20,
      status: "to_learn",
      cefr_level: "A2",
      pronunciation: "/baŋk/",
      pronunciations: { us: "/bæŋk/", uk: "/baŋk/" },
      translation: "银行",
      primary_definition: "A financial institution.",
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          localized_definition: "银行",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [
            {
              id: "example-1",
              sentence: "She went to the bank before work.",
              difficulty: "A1",
              translation: "她上班前去了银行。",
              linked_entries: [],
            },
            {
              id: "example-2",
              sentence: "The bank closes at five.",
              difficulty: "A1",
              translation: "银行五点关门。",
              linked_entries: [],
            },
          ],
          translations: [{ id: "translation-1", language: "zh-Hans", translation: "银行" }],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByText("She went to the bank before work.")).toBeInTheDocument();
    expect(screen.getByText("她上班前去了银行。")).toBeInTheDocument();
    expect(screen.getByText("The bank closes at five.")).toBeInTheDocument();
    expect(screen.getByText("银行五点关门。")).toBeInTheDocument();
  });

  it("renders two ordered examples for a phrase sense when both exist", async () => {
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
          localized_definition: "依靠",
          part_of_speech: "phrasal verb",
          usage_note: "Common spoken phrase.",
          localized_usage_note: "口语中常见。",
          register: "neutral",
          primary_domain: "general",
          secondary_domains: ["relationships"],
          grammar_patterns: ["bank on + noun"],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [
            {
              id: "example-1",
              sentence: "You can bank on me.",
              difficulty: "A2",
              translation: "你可以依靠我。",
              linked_entries: [],
            },
            {
              id: "example-2",
              sentence: "We bank on their support every year.",
              difficulty: "B1",
              translation: "我们每年都依靠他们的支持。",
              linked_entries: [],
            },
          ],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText("You can bank on me.")).toBeInTheDocument();
    expect(screen.getByText("你可以依靠我。")).toBeInTheDocument();
    expect(screen.getByText("We bank on their support every year.")).toBeInTheDocument();
    expect(screen.getByText("我们每年都依靠他们的支持。")).toBeInTheDocument();
  });

  it("persists accent changes and plays learner audio from the selected accent", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "Bank",
      normalized_form: "bank",
      browse_rank: 20,
      status: "to_learn",
      cefr_level: "A2",
      pronunciation: "/baŋk/",
      pronunciations: { us: "/bæŋk/", uk: "/baŋk/" },
      translation: "银行",
      primary_definition: "A financial institution.",
      voice_assets: [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en-US",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
        {
          id: "voice-uk",
          content_scope: "word",
          locale: "en-GB",
          playback_url: "/api/words/voice-assets/voice-uk/content",
        },
      ],
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          localized_definition: "银行",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [{ id: "translation-1", language: "zh-Hans", translation: "银行" }],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByRole("button", { name: "Play audio for Bank" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use UK accent" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("/baŋk/")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Use US accent" }));

    await waitFor(() =>
      expect(mockUpdateUserPreferences).toHaveBeenCalledWith({
        accent_preference: "us",
        translation_locale: "zh-Hans",
        knowledge_view_preference: "cards",
        show_translations_by_default: true,
      }),
    );

    await waitFor(() => expect(screen.getByText("/bæŋk/")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Play audio for Bank" }));

    expect(mockPlayLearnerEntryAudio).toHaveBeenCalledWith(
      [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en-US",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
        {
          id: "voice-uk",
          content_scope: "word",
          locale: "en-GB",
          playback_url: "/api/words/voice-assets/voice-uk/content",
        },
      ],
      "us",
      {
        contentScope: "word",
      },
    );
  });

  it("plays definition and example audio for the active meaning", async () => {
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
      voice_assets: [
        {
          id: "voice-definition-us",
          content_scope: "definition",
          meaning_id: "meaning-1",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-definition-us/content",
        },
        {
          id: "voice-example-us",
          content_scope: "example",
          meaning_example_id: "example-1",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-example-us/content",
        },
      ],
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          localized_definition: "银行",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [
            {
              id: "example-1",
              sentence: "I deposited cash at the bank.",
              difficulty: "A2",
              translation: "我在银行存了现金。",
            },
          ],
          translations: [{ id: "translation-1", language: "zh-Hans", translation: "银行" }],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByRole("button", { name: "Play definition audio for Bank" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Play example audio for Bank" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Play definition audio for Bank" }));
    expect(mockPlayLearnerEntryAudio).toHaveBeenCalledWith(
      expect.any(Array),
      "uk",
      {
        contentScope: "definition",
        meaningId: "meaning-1",
        phraseSenseId: undefined,
      },
    );

    fireEvent.click(screen.getByRole("button", { name: "Play example audio for Bank" }));
    expect(mockPlayLearnerEntryAudio).toHaveBeenCalledWith(
      expect.any(Array),
      "uk",
      {
        contentScope: "example",
        meaningExampleId: "example-1",
        phraseSenseExampleId: undefined,
      },
    );
  });

  it("shows review scheduling controls on the real detail page and advances the stored review session", async () => {
    const push = jest.fn();
    mockUseRouter.mockReturnValue({ push } as never);
    window.history.pushState({}, "", "/word/word-1?return_to=review&resume=1");
    window.sessionStorage.setItem(
      "learner-review-session-v1",
      JSON.stringify({
        cards: [
          {
            id: "state-1",
            queue_item_id: "state-1",
            word: "Bank",
            definition: "A financial institution.",
            review_mode: "mcq",
            prompt: {
              prompt_token: "prompt-state-1",
            },
            detail: {
              entry_type: "word",
              entry_id: "word-1",
              display_text: "Bank",
            },
            schedule_options: [
              { value: "1d", label: "Tomorrow", is_default: true },
              { value: "7d", label: "In a week", is_default: false },
            ],
          },
          {
            id: "state-2",
            queue_item_id: "state-2",
            word: "Lender",
            definition: "A person or organization that lends money.",
          },
        ],
        currentIndex: 0,
        phase: "reveal",
        revealState: {
          outcome: "correct_tested",
          detail: {
            entry_type: "word",
            entry_id: "word-1",
            display_text: "Bank",
            primary_definition: "A financial institution.",
            compare_with: [],
            meaning_count: 1,
            remembered_count: 0,
            meanings: [],
          },
          scheduleOptions: [
            { value: "1d", label: "Tomorrow", is_default: true },
            { value: "7d", label: "In a week", is_default: false },
          ],
          selectedSchedule: "1d",
          selectedOptionId: "A",
          persisted: false,
        },
        typedAnswer: "",
      }),
    );
    mockPost.mockResolvedValue({} as never);
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "Bank",
      normalized_form: "bank",
      browse_rank: 20,
      status: "learning",
      cefr_level: "A2",
      pronunciation: "/baŋk/",
      translation: "银行",
      voice_assets: [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en-US",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
      ],
      primary_definition: "A financial institution.",
      meanings: [
        {
          id: "meaning-1",
          definition: "A financial institution.",
          localized_definition: "银行",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect((await screen.findAllByText(/next review scheduled/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/scheduled time will be set when you continue review/i)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/approximately:/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^override$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /back to review/i })).not.toBeInTheDocument();
    expect(mockPlayLearnerEntryAudio).toHaveBeenCalledWith(
      [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en-US",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
      ],
      "uk",
      { contentScope: "word" },
    );

    fireEvent.click(screen.getByRole("button", { name: /^override$/i }));
    expect(screen.queryByText(/scheduled release:/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/choose next review timing/i), { target: { value: "7d" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm next review change/i }));
    fireEvent.click(screen.getByRole("button", { name: /continue review/i }));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        "/reviews/queue/state-1/submit",
        expect.objectContaining({
          confirm: true,
          prompt_token: "prompt-state-1",
          selected_option_id: "A",
          schedule_override: "7d",
        }),
      ),
    );
    expect(push).toHaveBeenCalledWith("/review?resume=1");
    expect(JSON.parse(window.sessionStorage.getItem("learner-review-session-v1") || "{}")).toEqual(
      expect.objectContaining({
        currentIndex: 1,
        phase: "challenge",
      }),
    );
  });

  it("persists next-review changes from the detail bottom bar for queued entries", async () => {
    mockPut.mockResolvedValue({
      queue_item_id: "queue-1",
      due_review_date: "2026-04-10",
      min_due_at_utc: "2026-04-10T00:00:00+00:00",
      current_schedule_value: "7d",
      current_schedule_label: "In a week",
      schedule_options: [
        { value: "10m", label: "Later today", is_default: false },
        { value: "1d", label: "Tomorrow", is_default: true },
        { value: "7d", label: "In a week", is_default: false },
      ],
    } as never);
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "bank on",
      normalized_form: "bank on",
      browse_rank: 141,
      status: "learning",
      cefr_level: "B1",
      pronunciation: null,
      pronunciations: {},
      translation: "依赖",
      primary_definition: "To depend on someone.",
      review_queue: {
        queue_item_id: "queue-1",
        due_review_date: "2026-04-04",
        min_due_at_utc: "2026-04-04T00:00:00+00:00",
        current_schedule_value: "1d",
        current_schedule_label: "Tomorrow",
        schedule_options: [
          { value: "10m", label: "Later today", is_default: false },
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To depend on someone.",
          localized_definition: "依赖",
          part_of_speech: "phrasal_verb",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText(/next review scheduled: tomorrow/i)).toBeInTheDocument();
    expect(
      screen.getByText(`Scheduled release: ${formatReviewTime("2026-04-04T00:00:00+00:00")}`),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^override$/i }));
    expect(screen.getByLabelText(/choose next review timing/i)).toHaveValue("1d");
    fireEvent.change(screen.getByLabelText(/choose next review timing/i), { target: { value: "7d" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm next review change/i }));

    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith("/reviews/queue/queue-1/schedule", {
        schedule_override: "7d",
      }),
    );
    expect(await screen.findByText(/next review scheduled: in a week/i)).toBeInTheDocument();
    expect(
      screen.getByText(`Scheduled release: ${formatReviewTime("2026-04-10T00:00:00+00:00")}`),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /override \(manual override\)/i })).toBeInTheDocument();
  });

  it("does not update the queued next review when the manual override sheet is dismissed", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "bank on",
      normalized_form: "bank on",
      browse_rank: 141,
      status: "learning",
      cefr_level: "B1",
      pronunciation: null,
      pronunciations: {},
      translation: "依赖",
      primary_definition: "To depend on someone.",
      review_queue: {
        queue_item_id: "queue-1",
        next_review_at: "2026-04-04T00:00:00+00:00",
        current_schedule_value: "never_for_now",
        current_schedule_label: "Pause review",
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "never_for_now", label: "Pause review", is_default: false },
        ],
      },
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To depend on someone.",
          localized_definition: "依赖",
          part_of_speech: "phrasal_verb",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText(/next review scheduled: pause review/i)).toBeInTheDocument();
    expect(
      screen.getByText(`Scheduled release: ${formatReviewTime("2026-04-04T00:00:00+00:00")}`),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /override \(manual override\)/i }));
    expect(screen.getByLabelText(/choose next review timing/i)).toHaveValue("never_for_now");
    fireEvent.change(screen.getByLabelText(/choose next review timing/i), { target: { value: "1d" } });
    fireEvent.click(screen.getByRole("button", { name: /leave current schedule/i }));

    expect(mockPut).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/choose next review timing/i)).not.toBeInTheDocument();
    expect(screen.getByText(/next review scheduled: pause review/i)).toBeInTheDocument();
  });

  it("shows next-review controls for learning entries even when no next review date exists yet", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "drum",
      normalized_form: "drum",
      browse_rank: 2400,
      status: "learning",
      cefr_level: "A2",
      pronunciation: null,
      pronunciations: {},
      translation: "鼓",
      primary_definition: "A percussion instrument.",
      review_queue: {
        queue_item_id: "queue-drum",
        next_review_at: null,
        current_schedule_value: "1d",
        current_schedule_label: "Tomorrow",
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
      meanings: [
        {
          id: "meaning-1",
          definition: "A percussion instrument.",
          localized_definition: "鼓",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByText(/next review scheduled: tomorrow/i)).toBeInTheDocument();
    expect(screen.queryByText(/approximately:/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^override$/i })).toBeInTheDocument();
  });

  it("renders detail next-review timing from min_due_at_utc when next_review_at is absent", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "bank on",
      normalized_form: "bank on",
      browse_rank: 141,
      status: "learning",
      cefr_level: "B1",
      pronunciation: null,
      pronunciations: {},
      translation: "依赖",
      primary_definition: "To depend on someone.",
      review_queue: {
        queue_item_id: "queue-1",
        next_review_at: null,
        due_review_date: "2026-04-11",
        min_due_at_utc: "2026-04-10T18:00:00Z",
        current_schedule_value: "1d",
        current_schedule_label: "Tomorrow",
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To depend on someone.",
          localized_definition: "依赖",
          part_of_speech: "phrasal_verb",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    } as never);

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText(/next review scheduled: in a week/i)).toBeInTheDocument();
    expect(
      screen.getByText(`Scheduled release: ${formatReviewTime("2026-04-10T18:00:00Z")}`),
    ).toBeInTheDocument();
  });

  it("keeps the canonical next-review summary visible when no exact release time or override options exist", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "bank on",
      normalized_form: "bank on",
      browse_rank: 141,
      status: "learning",
      cefr_level: "B1",
      pronunciation: null,
      pronunciations: {},
      translation: "依赖",
      primary_definition: "To depend on someone.",
      review_queue: {
        queue_item_id: "queue-1",
        next_review_at: null,
        current_schedule_value: "1d",
        current_schedule_label: "Tomorrow",
        schedule_options: [],
      },
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To depend on someone.",
          localized_definition: "依赖",
          part_of_speech: "phrasal_verb",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
        },
      ],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    } as never);

    render(<KnowledgeEntryDetailPage entryType="phrase" entryId="phrase-1" />);

    expect(await screen.findByText(/next review scheduled: tomorrow/i)).toBeInTheDocument();
    expect(screen.queryByText(/scheduled release:/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^override/i })).not.toBeInTheDocument();
  });

  it("clears next-review controls immediately when an entry is marked as already knew", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "drum",
      normalized_form: "drum",
      browse_rank: 2400,
      status: "learning",
      cefr_level: "A2",
      pronunciation: null,
      pronunciations: {},
      translation: "鼓",
      primary_definition: "A percussion instrument.",
      review_queue: {
        queue_item_id: "queue-drum",
        next_review_at: null,
        current_schedule_value: "1d",
        current_schedule_label: "Tomorrow",
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
      meanings: [
        {
          id: "meaning-1",
          definition: "A percussion instrument.",
          localized_definition: "鼓",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });
    mockPut.mockResolvedValueOnce({ entry_type: "word", entry_id: "word-1", status: "known" } as never);

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByText(/^Next Review$/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /already knew/i }));

    await waitFor(() => expect(screen.queryByText(/^Next Review$/i)).not.toBeInTheDocument());
  });

  it("clears next-review controls immediately when an entry is moved back to should learn", async () => {
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "drum",
      normalized_form: "drum",
      browse_rank: 2400,
      status: "known",
      cefr_level: "A2",
      pronunciation: null,
      pronunciations: {},
      translation: "鼓",
      primary_definition: "A percussion instrument.",
      review_queue: {
        queue_item_id: "queue-drum",
        next_review_at: null,
        current_schedule_value: "1d",
        current_schedule_label: "Tomorrow",
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
      meanings: [
        {
          id: "meaning-1",
          definition: "A percussion instrument.",
          localized_definition: "鼓",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });
    mockPut.mockResolvedValueOnce({ entry_type: "word", entry_id: "word-1", status: "to_learn" } as never);

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    expect(await screen.findByText(/^Next Review$/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /should learn/i }));

    await waitFor(() => expect(screen.queryByText(/^Next Review$/i)).not.toBeInTheDocument());
  });

  it("opens the review flow after Learn Now succeeds", async () => {
    const push = jest.fn();
    mockUseRouter.mockReturnValue({ push } as never);
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "drum",
      normalized_form: "drum",
      browse_rank: 2400,
      status: "to_learn",
      cefr_level: "A2",
      pronunciation: null,
      pronunciations: {},
      translation: "鼓",
      primary_definition: "A percussion instrument.",
      review_queue: null,
      meanings: [
        {
          id: "meaning-1",
          definition: "A percussion instrument.",
          localized_definition: "鼓",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });
    mockPut.mockResolvedValueOnce({ entry_type: "word", entry_id: "word-1", status: "learning" } as never);

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    fireEvent.click(await screen.findByRole("button", { name: /learn now/i }));

    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith("/knowledge-map/entries/word/word-1/status", {
        status: "learning",
      }),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/review?entry_type=word&entry_id=word-1"),
    );
  });

  it("shows an inline error when Learn Now fails", async () => {
    const push = jest.fn();
    mockUseRouter.mockReturnValue({ push } as never);
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      display_text: "drum",
      normalized_form: "drum",
      browse_rank: 2400,
      status: "to_learn",
      cefr_level: "A2",
      pronunciation: null,
      pronunciations: {},
      translation: "鼓",
      primary_definition: "A percussion instrument.",
      review_queue: null,
      meanings: [
        {
          id: "meaning-1",
          definition: "A percussion instrument.",
          localized_definition: "鼓",
          part_of_speech: "noun",
          usage_note: null,
          localized_usage_note: null,
          register: null,
          primary_domain: null,
          secondary_domains: [],
          grammar_patterns: [],
          synonyms: [],
          antonyms: [],
          collocations: [],
          examples: [],
          translations: [],
          relations: [],
        },
      ],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });
    mockPut.mockRejectedValueOnce(new Error("Status update failed"));

    render(<KnowledgeEntryDetailPage entryType="word" entryId="word-1" />);

    fireEvent.click(await screen.findByRole("button", { name: /learn now/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Status update failed");
    expect(push).not.toHaveBeenCalled();
  });
});
