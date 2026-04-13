import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchPage from "@/app/search/page";
import {
  getKnowledgeMapSearchHistory,
  searchKnowledgeMap,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client");
jest.mock("next/link", () => {
  type MockLinkProps = React.ComponentPropsWithoutRef<"a"> & { href: string };
  const MockLink = ({ children, href, onClick, ...props }: MockLinkProps) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

describe("SearchPage", () => {
  const mockGetKnowledgeMapSearchHistory = getKnowledgeMapSearchHistory as jest.MockedFunction<typeof getKnowledgeMapSearchHistory>;
  const mockSearchKnowledgeMap = searchKnowledgeMap as jest.MockedFunction<typeof searchKnowledgeMap>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockGetKnowledgeMapSearchHistory.mockResolvedValue({
      items: [
        {
          query: "bank",
          entry_type: "word",
          entry_id: "word-1",
          last_searched_at: "2026-03-24T00:00:00Z",
        },
      ],
    });
    mockSearchKnowledgeMap.mockResolvedValue({
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
          status: "learning",
          cefr_level: "B1",
          pronunciation: null,
          translation: null,
          primary_definition: "To rely on someone.",
          part_of_speech: null,
          phrase_kind: "phrasal_verb",
        },
      ],
    });
  });

  it("loads search history and standalone results", async () => {
    const user = userEvent.setup();
    render(<SearchPage />);

    expect(await screen.findByRole("link", { name: "bank" })).toHaveAttribute("href", "/word/word-1");

    await user.type(screen.getByPlaceholderText(/search words and phrases/i), "ba");

    expect(await screen.findByRole("link", { name: /bank/i })).toHaveAttribute("href", "/word/word-1");
    expect(await screen.findByRole("link", { name: /bank on/i })).toHaveAttribute("href", "/phrase/phrase-1");
    expect(screen.getAllByText("To rely on someone.").length).toBeGreaterThan(0);
    expect(screen.queryByText("Pronunciation unavailable")).not.toBeInTheDocument();
  });

  it("clears stale results when the query drops below two characters", async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    render(<SearchPage />);

    await screen.findByRole("link", { name: "bank" });
    await user.type(screen.getByPlaceholderText(/search words and phrases/i), "ba");
    act(() => {
      jest.advanceTimersByTime(250);
    });

    expect(await screen.findByRole("link", { name: /bank on/i })).toHaveAttribute("href", "/phrase/phrase-1");

    await user.clear(screen.getByPlaceholderText(/search words and phrases/i));

    expect(screen.queryByRole("link", { name: /bank on/i })).not.toBeInTheDocument();

    jest.useRealTimers();
  });
});
