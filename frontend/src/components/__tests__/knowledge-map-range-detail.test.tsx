import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import { KnowledgeMapRangeDetail } from "@/components/knowledge-map-range-detail";
import {
  getKnowledgeMapEntryDetail,
  getKnowledgeMapRange,
  normalizeLearnerTranslation,
} from "@/lib/knowledge-map-client";
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
    getKnowledgeMapRange: jest.fn(),
    normalizeLearnerTranslation: jest.fn(actual.normalizeLearnerTranslation),
  };
});
jest.mock("@/lib/learner-audio", () => ({
  getPlayableLearnerAccents: jest.fn((voiceAssets) => {
    const locales = new Set((voiceAssets ?? []).map((asset: { locale?: string }) => asset.locale));
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
  playLearnerEntryAudio: jest.fn(),
}));
jest.mock("@/lib/user-preferences-client");

describe("KnowledgeMapRangeDetail", () => {
  const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
  const mockGetKnowledgeMapRange = getKnowledgeMapRange as jest.MockedFunction<typeof getKnowledgeMapRange>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<
    typeof getKnowledgeMapEntryDetail
  >;
  const mockNormalizeLearnerTranslation = normalizeLearnerTranslation as jest.MockedFunction<
    typeof normalizeLearnerTranslation
  >;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockUpdateUserPreferences = updateUserPreferences as jest.MockedFunction<typeof updateUserPreferences>;
  const mockPlayLearnerEntryAudio = playLearnerEntryAudio as jest.MockedFunction<typeof playLearnerEntryAudio>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({ push: jest.fn() } as never);
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "list",
      show_translations_by_default: true,
    });
    mockUpdateUserPreferences.mockResolvedValue({
      accent_preference: "us",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "list",
      show_translations_by_default: true,
    });
    mockPlayLearnerEntryAudio.mockResolvedValue(true);
  });

  it("renders both English definitions and localized translations in list view cards", async () => {
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

    render(<KnowledgeMapRangeDetail initialRangeStart={1} />);

    expect(await screen.findByTestId("knowledge-list-view")).toBeInTheDocument();
    expect(await screen.findByText("A financial institution.")).toBeInTheDocument();
    expect(await screen.findByText("银行", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(await screen.findByText("To rely on someone.")).toBeInTheDocument();
    expect(await screen.findByText("依靠", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("memoizes list translations across rerenders when the data is unchanged", async () => {
    mockGetKnowledgeMapRange.mockResolvedValue({
      range_start: 1,
      range_end: 100,
      previous_range_start: null,
      next_range_start: null,
      items: [
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
      meanings: [],
      senses: [
        {
          sense_id: "sense-1",
          definition: "To rely on someone.",
          localized_definition: "依靠",
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

    const { rerender } = render(<KnowledgeMapRangeDetail initialRangeStart={1} />);

    expect(await screen.findByText("依靠", {}, { timeout: 3000 })).toBeInTheDocument();
    await waitFor(() =>
      expect(
        mockNormalizeLearnerTranslation.mock.calls.filter(([value]) => value === "依靠"),
      ).toHaveLength(2),
    );
    const callCountBeforeRerender = mockNormalizeLearnerTranslation.mock.calls.length;

    rerender(<KnowledgeMapRangeDetail initialRangeStart={1} />);

    expect(mockNormalizeLearnerTranslation).toHaveBeenCalledTimes(callCountBeforeRerender);
  });

  it("hides placeholder translations instead of rendering them as learner data", async () => {
    mockGetKnowledgeMapRange.mockResolvedValue({
      range_start: 1,
      range_end: 100,
      previous_range_start: null,
      next_range_start: null,
      items: [
        {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "Bank on",
          normalized_form: "bank on",
          browse_rank: 21,
          status: "undecided",
          cefr_level: "B1",
          pronunciation: null,
          translation: "Translation unavailable",
          primary_definition: "To rely on someone.",
          part_of_speech: null,
          phrase_kind: "phrasal_verb",
        },
      ],
    });
    mockGetKnowledgeMapEntryDetail.mockResolvedValue({
      entry_type: "phrase",
      entry_id: "phrase-1",
      display_text: "Bank on",
      normalized_form: "bank on",
      browse_rank: 21,
      status: "undecided",
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

    render(<KnowledgeMapRangeDetail initialRangeStart={1} />);

    expect(await screen.findByText("To rely on someone.")).toBeInTheDocument();
    expect(screen.queryByText("Translation unavailable")).not.toBeInTheDocument();
  });

  it("supports quick accent switching and playback from the learner range list", async () => {
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
          voice_assets: [
            {
              id: "voice-us",
              content_scope: "word",
              locale: "en_us",
              playback_url: "/api/words/voice-assets/voice-us/content",
            },
            {
              id: "voice-uk",
              content_scope: "word",
              locale: "en_gb",
              playback_url: "/api/words/voice-assets/voice-uk/content",
            },
          ],
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
      voice_assets: [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
        {
          id: "voice-uk",
          content_scope: "word",
          locale: "en_gb",
          playback_url: "/api/words/voice-assets/voice-uk/content",
        },
      ],
      meanings: [],
      senses: [],
      relation_groups: [],
      confusable_words: [],
      previous_entry: null,
      next_entry: null,
    });

    render(<KnowledgeMapRangeDetail initialRangeStart={1} />);

    expect(await screen.findByRole("button", { name: "Play audio for Bank" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use US accent" }));

    await waitFor(() =>
      expect(mockUpdateUserPreferences).toHaveBeenCalledWith({
        accent_preference: "us",
        translation_locale: "zh-Hans",
        knowledge_view_preference: "list",
        show_translations_by_default: true,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Play audio for Bank" }));

    expect(mockPlayLearnerEntryAudio).toHaveBeenCalledWith(
      [
        {
          id: "voice-us",
          content_scope: "word",
          locale: "en_us",
          playback_url: "/api/words/voice-assets/voice-us/content",
        },
        {
          id: "voice-uk",
          content_scope: "word",
          locale: "en_gb",
          playback_url: "/api/words/voice-assets/voice-uk/content",
        },
      ],
      "us",
    );
  });
});
