import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams } from "next/navigation";
import KnowledgeListPage from "@/app/knowledge-list/[status]/page";
import { getKnowledgeMapList } from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  useParams: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client");

describe("KnowledgeListPage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockGetKnowledgeMapList = getKnowledgeMapList as jest.MockedFunction<typeof getKnowledgeMapList>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
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
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
  });

  it("renders the known list with search and sort controls", async () => {
    mockUseParams.mockReturnValue({ status: "known" } as any);

    render(<KnowledgeListPage />);

    expect(await screen.findByText(/knew words/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /alphabetic/i })).toBeInTheDocument();
    expect(await screen.findByText("The")).toBeInTheDocument();
    expect((await screen.findAllByText("Already knew")).length).toBeGreaterThan(0);
  });

  it("cycles through alphabetic, hardest first, and easiest first sort options", async () => {
    const user = userEvent.setup();
    mockUseParams.mockReturnValue({ status: "learning" } as any);

    render(<KnowledgeListPage />);

    const sortButton = await screen.findByRole("button", { name: /alphabetic/i });
    await user.click(sortButton);
    expect(screen.getByRole("button", { name: /hardest first/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /hardest first/i }));
    expect(screen.getByRole("button", { name: /easiest first/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /easiest first/i }));
    expect(screen.getByRole("button", { name: /alphabetic/i })).toBeInTheDocument();
  });

  it("maps the new route to the undecided learner list", async () => {
    mockUseParams.mockReturnValue({ status: "new" } as any);

    render(<KnowledgeListPage />);

    await screen.findByText(/new words/i);
    expect(mockGetKnowledgeMapList).toHaveBeenCalledWith(
      expect.objectContaining({ status: "new" }),
    );
  });
});
