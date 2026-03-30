import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LexiconDbInspectorPage from "@/app/lexicon/db-inspector/page";
import { browseLexiconInspectorEntries, getLexiconInspectorDetail } from "@/lib/lexicon-inspector-client";

jest.mock("@/lib/lexicon-inspector-client", () => ({
  browseLexiconInspectorEntries: jest.fn(),
  getLexiconInspectorDetail: jest.fn(),
}));

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("LexiconDbInspectorPage", () => {
  const mockBrowse = browseLexiconInspectorEntries as jest.Mock;
  const mockDetail = getLexiconInspectorDetail as jest.Mock;
  const originalFetch = global.fetch;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;
  const playMock = jest.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(global.HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: playMock,
    });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(["fake-mp3"], { type: "audio/mpeg" }),
    } as Response);
    URL.createObjectURL = jest.fn(() => "blob:voice-1");
    URL.revokeObjectURL = jest.fn();
    mockBrowse.mockResolvedValue({
      items: [
        {
          id: "word-1",
          family: "word",
          display_text: "bank",
          normalized_form: "bank",
          language: "en",
          source_reference: "snapshot-001",
          cefr_level: "B1",
          frequency_rank: 100,
          secondary_label: "bæŋk",
          created_at: "2026-03-21T00:00:00Z",
        },
        {
          id: "phrase-1",
          family: "phrase",
          display_text: "break a leg",
          normalized_form: "break a leg",
          language: "en",
          source_reference: "snapshot-001",
          cefr_level: "B2",
          frequency_rank: null,
          secondary_label: "idiom",
          created_at: "2026-03-20T00:00:00Z",
        },
      ],
      total: 2,
      family: "all",
      q: null,
      limit: 10,
      offset: 0,
      has_more: false,
    });
    mockDetail.mockResolvedValue({
      family: "word",
      id: "word-1",
      display_text: "bank",
      normalized_form: "bank",
      language: "en",
      cefr_level: "B1",
      frequency_rank: 100,
      phonetics: { au: { ipa: "/bɐŋk/", confidence: 0.97 }, us: { ipa: "/bæŋk/", confidence: 0.99 }, uk: { ipa: "/bæŋk/", confidence: 0.98 } },
      phonetic: "bæŋk",
      phonetic_source: "lexicon_snapshot",
      phonetic_confidence: 0.98,
      learner_part_of_speech: ["noun", "verb"],
      confusable_words: [{ word: "bench", reason: "form" }],
      word_forms: { plural_forms: ["banks"] },
      source_type: "lexicon_snapshot",
      source_reference: "snapshot-001",
      learner_generated_at: "2026-03-21T00:00:00Z",
      created_at: "2026-03-21T00:00:00Z",
      voice_assets: [
        {
          id: "voice-1",
          content_scope: "word",
          meaning_id: null,
          meaning_example_id: null,
          relative_path: "word_bank/word/en_us/female-word-123.mp3",
          locale: "en-US",
          voice_role: "female",
          provider: "google",
          family: "neural2",
          voice_id: "en-US-Neural2-C",
          profile_key: "word",
          audio_format: "mp3",
          mime_type: "audio/mpeg",
          playback_url: "/api/words/voice-assets/voice-1/content",
          playback_route_kind: "backend_content_route",
          primary_target_kind: "local",
          primary_target_base: "/tmp/voice",
          resolved_target_url: "/tmp/voice/word_bank/word/en_us/female-word-123.mp3",
          status: "generated",
          generated_at: "2026-03-21T00:00:00Z",
        },
      ],
      voice_paths: {
        word: {
          playback_url: "/api/words/voice-assets/voice-1/content",
          resolved_target_kind: "local",
          resolved_target_base: "/tmp/voice",
        },
        definition: null,
        example: null,
      },
      meanings: [
        {
          id: "meaning-1",
          definition: "a financial institution",
          part_of_speech: "noun",
          primary_domain: "money",
          secondary_domains: ["finance"],
          register_label: "neutral",
          grammar_patterns: ["countable noun"],
          usage_note: "Common everyday sense.",
          example_sentence: "She went to the bank.",
          source: "compiled",
          source_reference: "snapshot-001",
          learner_generated_at: "2026-03-21T00:00:00Z",
          order_index: 0,
          examples: [{ id: "example-1", sentence: "She went to the bank.", difficulty: "A1", order_index: 0 }],
          relations: [{ id: "relation-1", relation_type: "confusable", related_word: "bench" }],
          translations: [{ id: "translation-1", language: "es", translation: "banco" }],
        },
      ],
      enrichment_runs: [],
    });
  });

  afterAll(() => {
    global.fetch = originalFetch;
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  });

  it("renders browse filters and loads detail for the selected entry", async () => {
    const user = userEvent.setup();
    window.history.pushState({}, "", "/lexicon/db-inspector?snapshot=words-100-20260312");
    render(<LexiconDbInspectorPage />);

    await waitFor(() => expect(screen.getByTestId("lexicon-db-inspector-page")).toBeInTheDocument());
    expect(screen.getByTestId("lexicon-db-inspector-context")).toHaveTextContent("Snapshot: words-100-20260312");
    await waitFor(() =>
      expect(mockBrowse).toHaveBeenCalledWith({
        family: "all",
        sort: "updated_desc",
        limit: 10,
        offset: 0,
        q: undefined,
      }),
    );
    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith("word", "word-1"));

    await user.selectOptions(screen.getByTestId("lexicon-db-inspector-family-filter"), "phrase");
    await waitFor(() =>
      expect(mockBrowse).toHaveBeenLastCalledWith({
        family: "phrase",
        sort: "updated_desc",
        limit: 10,
        offset: 0,
        q: undefined,
      }),
    );

    await user.type(screen.getByTestId("lexicon-db-inspector-search-input"), "bank");
    await waitFor(() =>
      expect(mockBrowse).toHaveBeenLastCalledWith({
        family: "phrase",
        sort: "updated_desc",
        limit: 10,
        offset: 0,
        q: "bank",
      }),
    );

    expect(screen.getByText("Stored phonetics")).toBeInTheDocument();
    expect(screen.getByText(/AU: \/bɐŋk\//i)).toBeInTheDocument();
    expect(screen.getByText(/US: \/bæŋk\//i)).toBeInTheDocument();
    expect(screen.getByText(/UK: \/bæŋk\//i)).toBeInTheDocument();
    expect(screen.getByText("a financial institution")).toBeInTheDocument();
    expect(screen.getByText(/Common everyday sense\./i)).toBeInTheDocument();
    expect(screen.getByText(/banco/i)).toBeInTheDocument();
    expect(screen.getByText(/Word · en-US · female/i)).toBeInTheDocument();
    expect(screen.getByText(/relative: word_bank\/word\/en_us\/female-word-123\.mp3/i)).toBeInTheDocument();
    expect(screen.getByText(/resolved: \/tmp\/voice\/word_bank\/word\/en_us\/female-word-123\.mp3/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /play word voice asset en-us female/i })).toBeInTheDocument();
  });

  it("renders phrase senses with grouped examples and translations", async () => {
    const user = userEvent.setup();
    mockDetail.mockResolvedValueOnce({
      family: "word",
      id: "word-1",
      display_text: "bank",
      normalized_form: "bank",
      language: "en",
      cefr_level: "B1",
      frequency_rank: 100,
      phonetics: { us: { ipa: "/bæŋk/" } },
      phonetic: "bæŋk",
      phonetic_source: "lexicon_snapshot",
      phonetic_confidence: 0.98,
      learner_part_of_speech: ["noun"],
      confusable_words: [],
      word_forms: null,
      source_type: "lexicon_snapshot",
      source_reference: "snapshot-001",
      learner_generated_at: "2026-03-21T00:00:00Z",
      created_at: "2026-03-21T00:00:00Z",
      voice_assets: [],
      voice_paths: {
        word: null,
        definition: null,
        example: null,
      },
      meanings: [],
      enrichment_runs: [],
    });
    mockDetail.mockResolvedValueOnce({
      family: "phrase",
      id: "phrase-1",
      display_text: "break a leg",
      normalized_form: "break a leg",
      language: "en",
      cefr_level: "B2",
      source_type: "lexicon_snapshot",
      source_reference: "snapshot-001",
      phrase_kind: "idiom",
      register_label: "informal",
      brief_usage_note: "used before performances",
      confidence_score: 0.91,
      generated_at: "2026-03-20T00:00:00Z",
      seed_metadata: { raw_reviewed_as: "idiom" },
      compiled_payload: { entry_id: "ph_break_a_leg" },
      voice_assets: [],
      voice_paths: {
        word: null,
        definition: {
          playback_url: "/api/words/voice-assets/voice-2/content",
          resolved_target_kind: "local",
          resolved_target_base: "/tmp/voice",
        },
        example: null,
      },
      senses: [
        {
          sense_id: "phrase-1",
          definition: "good luck",
          part_of_speech: "phrase",
          grammar_patterns: ["say + phrase"],
          usage_note: "Used before a performance.",
          examples: [{ id: "ex-1", sentence: "Break a leg tonight.", difficulty: "A1", order_index: 0 }],
          translations: [{ locale: "es", definition: "buena suerte", usage_note: "antes de actuar", examples: ["Buena suerte esta noche."] }],
        },
      ],
      created_at: "2026-03-20T00:00:00Z",
    });

    render(<LexiconDbInspectorPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^break a leg/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^break a leg/i }));

    await waitFor(() => expect(screen.getByText("good luck")).toBeInTheDocument());
    expect(screen.getByText("Seed metadata")).toBeInTheDocument();
    expect(screen.getByText("Break a leg tonight.")).toBeInTheDocument();
    expect(screen.getByText(/es: buena suerte/i)).toBeInTheDocument();
    expect(screen.getByText(/Used before a performance\./i)).toBeInTheDocument();
    expect(screen.getByText("Voice assets")).toBeInTheDocument();
    expect(screen.queryByText("Voice paths by scope")).not.toBeInTheDocument();
  });

  it("loads voice playback through an authenticated fetch before playing", async () => {
    const user = userEvent.setup();

    render(<LexiconDbInspectorPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: /play word voice asset en-us female/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /play word voice asset en-us female/i }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith("/api/words/voice-assets/voice-1/content", {
        headers: {
          Authorization: "Bearer active-token",
        },
      }),
    );
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(playMock).toHaveBeenCalled();
  });
});
