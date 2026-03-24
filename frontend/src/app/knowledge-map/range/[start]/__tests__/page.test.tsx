import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams, useRouter } from "next/navigation";
import KnowledgeMapRangePage from "@/app/knowledge-map/range/[start]/page";
import {
  getKnowledgeMapEntryDetail,
  getKnowledgeMapRange,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  useParams: jest.fn(),
  useRouter: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client");

describe("KnowledgeMapRangePage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
  const mockGetKnowledgeMapRange = getKnowledgeMapRange as jest.MockedFunction<typeof getKnowledgeMapRange>;
  const mockGetKnowledgeMapEntryDetail = getKnowledgeMapEntryDetail as jest.MockedFunction<typeof getKnowledgeMapEntryDetail>;
  const mockUpdateKnowledgeEntryStatus = updateKnowledgeEntryStatus as jest.MockedFunction<typeof updateKnowledgeEntryStatus>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseParams.mockReturnValue({ start: "1" } as never);
    mockUseRouter.mockReturnValue({ push: jest.fn() } as never);
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockGetKnowledgeMapRange.mockImplementation(async (rangeStart) => {
      if (rangeStart === 101) {
        return {
          range_start: 101,
          range_end: 200,
          previous_range_start: 1,
          next_range_start: 201,
          items: [
            {
              entry_type: "word",
              entry_id: "word-2",
              display_text: "To",
              normalized_form: "to",
              browse_rank: 2,
              status: "learning",
              cefr_level: "A1",
              pronunciation: "/tuː/",
              translation: "到",
              primary_definition: "Used to express motion or direction.",
              part_of_speech: "preposition",
              phrase_kind: null,
            },
          ],
        };
      }

      return {
        range_start: 1,
        range_end: 100,
        previous_range_start: null,
        next_range_start: 101,
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
      };
    });
    mockGetKnowledgeMapEntryDetail.mockImplementation(async (entryType, entryId) => {
      if (entryType === "word" && entryId === "word-1") {
        return {
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
              examples: [],
              translations: [
                { id: "translation-0", language: "ar", translation: "مصرف" },
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
        };
      }

      return {
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
            examples: [],
          },
        ],
        relation_groups: [],
        confusable_words: [],
        previous_entry: null,
        next_entry: null,
      };
    });
    mockUpdateKnowledgeEntryStatus.mockResolvedValue({
      entry_type: "word",
      entry_id: "word-1",
      status: "known",
    });
  });

  it("loads the selected range detail from the route param", async () => {
    render(<KnowledgeMapRangePage />);

    expect(await screen.findByText(/^knowledge map$/i)).toBeInTheDocument();
    expect(await screen.findByText(/range 1-100/i)).toBeInTheDocument();
    expect(await screen.findByTestId("knowledge-card-view")).toBeInTheDocument();
    expect(screen.getByTestId("knowledge-range-strip")).toBeInTheDocument();
    expect(screen.getByText("Bank")).toBeInTheDocument();
    expect(screen.getByText("银行")).toBeInTheDocument();
    expect(screen.queryByText("مصرف")).not.toBeInTheDocument();
    expect(mockGetKnowledgeMapRange).toHaveBeenCalledWith(1);
  });

  it("moves between previous and next ranges with the bottom range arrows", async () => {
    const user = userEvent.setup();
    render(<KnowledgeMapRangePage />);

    expect(await screen.findByRole("button", { name: /next range/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /next range/i }));

    await waitFor(() => {
      expect(mockGetKnowledgeMapRange).toHaveBeenCalledWith(101);
    });
  });

  it("keeps the selected entry and definition in sync when browsing across entries", async () => {
    const user = userEvent.setup();
    render(<KnowledgeMapRangePage />);

    expect(await screen.findByText("Bank")).toBeInTheDocument();
    expect(screen.getByText("A financial institution.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /next entry/i }));

    expect(await screen.findByText("Bank on")).toBeInTheDocument();
    expect(screen.getByText("To rely on someone.")).toBeInTheDocument();
    expect(mockGetKnowledgeMapEntryDetail).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("button", { name: /previous entry/i }));

    expect(await screen.findByText("Bank")).toBeInTheDocument();
    expect(screen.getByText("A financial institution.")).toBeInTheDocument();
    expect(mockGetKnowledgeMapEntryDetail).toHaveBeenCalledTimes(2);
  });
});
