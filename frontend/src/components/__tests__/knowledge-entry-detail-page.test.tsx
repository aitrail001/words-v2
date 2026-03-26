import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { KnowledgeEntryDetailPage } from "@/components/knowledge-entry-detail-page";
import { getKnowledgeMapEntryDetail } from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("@/lib/knowledge-map-client", () => {
  const actual = jest.requireActual("@/lib/knowledge-map-client");

  return {
    ...actual,
    getKnowledgeMapEntryDetail: jest.fn(),
    normalizeLearnerTranslation: jest.fn(actual.normalizeLearnerTranslation),
  };
});
jest.mock("@/lib/user-preferences-client");

describe("KnowledgeEntryDetailPage", () => {
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<
    typeof getKnowledgeMapEntryDetail
  >;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockNormalizeLearnerTranslation = jest.requireMock("@/lib/knowledge-map-client")
    .normalizeLearnerTranslation as jest.MockedFunction<
    typeof import("@/lib/knowledge-map-client").normalizeLearnerTranslation
  >;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
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
});
