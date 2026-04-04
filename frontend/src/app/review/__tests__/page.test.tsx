import { useRouter } from "next/navigation";
import { act, fireEvent, render, screen } from "@testing-library/react";
import ReviewPage from "@/app/review/page";
import { apiClient } from "@/lib/api-client";
import { useLearnerAudio } from "@/lib/learner-audio";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(() => ({ push: jest.fn() })),
}));

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

jest.mock("@/lib/learner-audio", () => ({
  useLearnerAudio: jest.fn(),
}));

jest.mock("@/lib/user-preferences-client", () => ({
  getUserPreferences: jest.fn(),
}));

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

describe("ReviewPage", () => {
  const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
  const mockGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>;
  const mockPost = apiClient.post as jest.MockedFunction<typeof apiClient.post>;
  const mockUseLearnerAudio = useLearnerAudio as jest.MockedFunction<typeof useLearnerAudio>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockPlay = jest.fn();
  const mockPush = jest.fn();
  let consoleErrorSpy: jest.SpyInstance;

  const renderPage = async () => {
    await act(async () => {
      render(<ReviewPage />);
    });
  };

  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockPlay.mockReset();
    mockPush.mockReset();
    mockGetUserPreferences.mockReset();
    window.sessionStorage.clear();
    window.history.pushState({}, "", "/review");
    consoleErrorSpy = jest.spyOn(console, "error").mockImplementation((message?: unknown) => {
      throw new Error(`Unexpected console.error during test: ${String(message)}`);
    });
    mockUseLearnerAudio.mockReturnValue({
      play: mockPlay,
      loadingUrl: null,
      playingUrl: null,
    });
    mockUseRouter.mockReturnValue({ push: mockPush } as never);
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "us",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
      review_depth_preset: "balanced",
      enable_confidence_check: true,
      enable_word_spelling: true,
      enable_audio_spelling: false,
      show_pictures_in_questions: false,
    });
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("redirects correct answers to the real detail page instead of rendering an inline reveal card", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-1",
        queue_item_id: "state-1",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-1",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: {
          entry_type: "word",
          entry_id: "word-1",
          display_text: "barely",
          primary_definition: "Only just, by a very small margin.",
          primary_example: "He barely made it through the door.",
          meaning_count: 1,
          remembered_count: 4,
          compare_with: [],
          meanings: [],
          audio_state: "not_available",
          coverage_summary: "deep_coverage",
        },
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
    ] as never);
    mockPost.mockResolvedValueOnce({
      outcome: "correct_tested",
      detail: {
        entry_type: "word",
        entry_id: "word-1",
        display_text: "barely",
        primary_definition: "Only just, by a very small margin.",
        primary_example: "He barely made it through the door.",
        meaning_count: 1,
        remembered_count: 4,
        compare_with: [],
        meanings: [],
        audio_state: "not_available",
        coverage_summary: "deep_coverage",
      },
      schedule_options: [
        { value: "1d", label: "Tomorrow", is_default: true },
        { value: "7d", label: "In a week", is_default: false },
      ],
    } as never);

    await renderPage();

    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: /a barely/i }));
    });

    expect(mockPush).toHaveBeenCalledWith("/word/word-1?return_to=review&resume=1");
    expect(screen.queryByTestId("review-reveal-state")).not.toBeInTheDocument();

    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-1/submit",
      expect.objectContaining({
        selected_option_id: "A",
        prompt_token: "prompt-state-1",
        confirm: false,
      }),
    );
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  it("only offers show-meaning as the non-confident path during active review prompts", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-1",
        queue_item_id: "state-1",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-1",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
    ] as never);

    await renderPage();

    expect(await screen.findByTestId("review-active-state")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /i remember it/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show meaning/i })).toBeInTheDocument();
  });

  it("shows a single replay button for audio-to-definition prompts", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-1",
        queue_item_id: "state-1",
        word: "as it is",
        definition: "In its current condition.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "audio_to_definition",
          prompt_token: "prompt-state-1",
          stem: "Listen, then choose the best matching definition.",
          question: "",
          options: [
            { option_id: "A", label: "In its current condition." },
            { option_id: "B", label: "In a very dramatic way." },
          ],
          audio_state: "ready",
          audio: {
            preferred_playback_url: "/api/audio/as-it-is.mp3",
          },
        },
        detail: null,
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
    ] as never);

    await renderPage();

    expect(await screen.findByRole("button", { name: /replay audio/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^play audio$/i })).not.toBeInTheDocument();
  });

  it("keeps later due cards ready without recomputing them on demand", async () => {
    mockGet
      .mockResolvedValueOnce([
        {
          id: "state-1",
          queue_item_id: "state-1",
          word: "barely",
          definition: "Only just, by a very small margin.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "definition_to_entry",
            prompt_token: "prompt-state-1",
            stem: "Choose the word or phrase that matches this definition.",
            question: "Only just, by a very small margin.",
            options: [
              { option_id: "A", label: "Barely" },
              { option_id: "B", label: "Bravely" },
            ],
            audio_state: "not_available",
          },
          detail: {
            entry_type: "word",
            entry_id: "word-1",
            display_text: "barely",
            primary_definition: "Only just, by a very small margin.",
            primary_example: "He barely made it through the door.",
            meaning_count: 1,
            remembered_count: 4,
            compare_with: [],
            meanings: [],
            audio_state: "not_available",
            coverage_summary: "deep_coverage",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        },
        {
          id: "state-2",
          queue_item_id: "state-2",
          word: "resilient",
          definition: "Able to recover quickly from difficulty.",
          review_mode: null,
          prompt: null,
          detail: null,
          schedule_options: [{ value: "3d", label: "In 3 days", is_default: true }],
        },
      ] as never)
      .mockResolvedValueOnce({
        id: "state-2",
        queue_item_id: "state-2",
        word: "resilient",
        definition: "Able to recover quickly from difficulty.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-2",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Able to recover quickly from difficulty.",
          options: [
            { option_id: "A", label: "resilient" },
            { option_id: "B", label: "fragile" },
          ],
          audio_state: "not_available",
        },
        detail: {
          entry_type: "word",
          entry_id: "word-2",
          display_text: "resilient",
          primary_definition: "Able to recover quickly from difficulty.",
          primary_example: "Resilient teams adapt quickly.",
          meaning_count: 1,
          remembered_count: 1,
          compare_with: [],
          meanings: [],
          audio_state: "not_available",
          coverage_summary: "familiar_with_1_meaning",
        },
        schedule_options: [{ value: "3d", label: "In 3 days", is_default: true }],
      } as never);
    mockPost.mockResolvedValueOnce({
      outcome: "correct_tested",
      detail: {
        entry_type: "word",
        entry_id: "word-1",
        display_text: "barely",
        primary_definition: "Only just, by a very small margin.",
        primary_example: "He barely made it through the door.",
        meaning_count: 1,
        remembered_count: 4,
        compare_with: [],
        meanings: [],
        audio_state: "not_available",
        coverage_summary: "deep_coverage",
      },
      schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
    } as never);

    await renderPage();

    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: /a barely/i }));
    });
    expect(mockPush).toHaveBeenCalledWith("/word/word-1?return_to=review&resume=1");
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).not.toHaveBeenCalledWith("/reviews/queue/state-2");
  });

  it("shows the relearn step after a wrong answer", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-2",
        queue_item_id: "state-2",
        word: "jump the gun",
        definition: "To do something too soon.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-2",
          stem: "Choose the word or phrase that matches this definition.",
          question: "To do something too soon.",
          options: [
            { option_id: "A", label: "Miss the boat" },
            { option_id: "B", label: "Jump the gun" },
          ],
          audio_state: "not_available",
        },
        detail: {
          entry_type: "phrase",
          entry_id: "phrase-1",
          display_text: "jump the gun",
          primary_definition: "To do something too soon.",
          primary_example: "They jumped the gun and announced it early.",
          meaning_count: 2,
          remembered_count: 1,
          compare_with: [],
          meanings: [
            {
              id: "sense-1",
              definition: "To do something too soon.",
              example: "They jumped the gun and announced it early.",
            },
          ],
          audio_state: "not_available",
          coverage_summary: "partial_coverage",
        },
        schedule_options: [
          { value: "10m", label: "Later today", is_default: true },
        ],
      },
    ] as never);
    mockPost.mockResolvedValue({
      outcome: "wrong",
      detail: {
        entry_type: "phrase",
        entry_id: "phrase-1",
        display_text: "jump the gun",
        primary_definition: "To do something too soon.",
        primary_example: "They jumped the gun and announced it early.",
        meaning_count: 2,
        remembered_count: 1,
        compare_with: [],
        meanings: [
          {
            id: "sense-1",
            definition: "To do something too soon.",
            example: "They jumped the gun and announced it early.",
          },
        ],
        audio_state: "not_available",
      },
      schedule_options: [{ value: "10m", label: "Later today", is_default: true }],
    } as never);

    await renderPage();

    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: /a miss the boat/i }));
    });

    expect(await screen.findByTestId("review-relearn-state")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /finish learning/i })).toBeInTheDocument();
    expect(screen.getByText("jump the gun")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-2/submit",
      expect.objectContaining({
        selected_option_id: "A",
        prompt_token: "prompt-state-2",
      }),
    );
  });

  it("redirects correct typed recall answers to the detail page and does not finalize inline", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-3",
        queue_item_id: "state-3",
        word: "look up",
        definition: "To search for information.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "typed_recall",
          prompt_token: "prompt-state-3",
          stem: "Type the word or phrase that matches this definition.",
          question: "To search for information.",
          options: null,
          input_mode: "typed",
          audio_state: "not_available",
        },
        detail: {
          entry_type: "phrase",
          entry_id: "phrase-3",
          display_text: "look up",
          primary_definition: "To search for information.",
          primary_example: "Look up the address before you leave.",
          meaning_count: 1,
          remembered_count: 2,
          compare_with: [],
          meanings: [],
          audio_state: "not_available",
          coverage_summary: "familiar_with_1_meaning",
        },
        schedule_options: [
          { value: "3d", label: "In 3 days", is_default: true },
        ],
      },
    ] as never);

    mockPost.mockResolvedValue({
      outcome: "correct_tested",
      detail: {
        entry_type: "word",
        entry_id: "word-3",
        display_text: "look up",
        primary_definition: "To search for information.",
        primary_example: "Look up the address before you leave.",
        meaning_count: 1,
        remembered_count: 2,
        compare_with: [],
        meanings: [],
        audio_state: "not_available",
      },
      schedule_options: [{ value: "3d", label: "In 3 days", is_default: true }],
    } as never);

    await renderPage();

    fireEvent.change(await screen.findByPlaceholderText(/type the word or phrase/i), {
      target: { value: "  Look, up!! " },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /check answer/i }));
    });

    expect(await screen.findByTestId("review-redirecting-state")).toBeInTheDocument();
    expect(mockPush).toHaveBeenCalledWith("/word/word-3?return_to=review&resume=1");
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-3/submit",
      expect.objectContaining({
        typed_answer: "  Look, up!! ",
        confirm: false,
      }),
    );
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  it("turns failed typed recall into a guided relearn pass before advancing", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-4",
        queue_item_id: "state-4",
        word: "resilience",
        definition: "The capacity to recover quickly from difficulties.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "typed_recall",
          prompt_token: "prompt-state-4",
          stem: "Type the word or phrase that matches this definition.",
          question: "The capacity to recover quickly from difficulties.",
          options: null,
          input_mode: "typed",
          audio_state: "not_available",
        },
        detail: {
          entry_type: "word",
          entry_id: "word-4",
          display_text: "resilience",
          primary_definition: "The capacity to recover quickly from difficulties.",
          primary_example: "Resilience helps teams adapt to change.",
          meaning_count: 1,
          remembered_count: 2,
          compare_with: [],
        meanings: [
          {
            id: "meaning-4a",
            definition: "The capacity to recover quickly from difficulties.",
            example: "Resilience helps teams adapt to change.",
          },
          {
            id: "meaning-4b",
            definition: "An ability to recover after setbacks.",
            example: "Resilience grows with practice.",
          },
        ],
        audio_state: "not_available",
        coverage_summary: "familiar_with_1_meaning",
      },
        schedule_options: [
          { value: "10m", label: "Later today", is_default: true },
        ],
      },
    ] as never);
    mockPost.mockResolvedValue({
      outcome: "wrong",
      detail: {
        entry_type: "word",
        entry_id: "word-4",
        display_text: "resilience",
        primary_definition: "The capacity to recover quickly from difficulties.",
        primary_example: "Resilience helps teams adapt to change.",
        meaning_count: 1,
        remembered_count: 2,
        compare_with: [],
        meanings: [
          {
            id: "meaning-4a",
            definition: "The capacity to recover quickly from difficulties.",
            example: "Resilience helps teams adapt to change.",
          },
          {
            id: "meaning-4b",
            definition: "An ability to recover after setbacks.",
            example: "Resilience grows with practice.",
          },
        ],
        audio_state: "not_available",
      },
      schedule_options: [{ value: "10m", label: "Later today", is_default: true }],
    } as never);

    await renderPage();

    fireEvent.change(await screen.findByPlaceholderText(/type the word or phrase/i), {
      target: { value: "reliance" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /check answer/i }));
    });

    expect(await screen.findByTestId("review-relearn-state")).toBeInTheDocument();
    expect(screen.getByText(/learn this meaning/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next meaning/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next meaning/i }));
    expect(await screen.findByText(/an ability to recover after setbacks\./i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /finish learning/i })).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-4/submit",
      expect.objectContaining({
        typed_answer: "reliance",
      }),
    );
  });

  it("nudges the learner to type an answer before checking typed recall", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-typed-empty",
        queue_item_id: "state-typed-empty",
        word: "look up",
        definition: "To search for information.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "typed_recall",
          prompt_token: "prompt-state-typed-empty",
          stem: "Type the word or phrase that matches this definition.",
          question: "To search for information.",
          options: null,
          input_mode: "typed",
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    await renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /check answer/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/type your answer before checking/i);
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("auto-plays typed recall audio and offers a replay button", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-typed-audio",
        queue_item_id: "state-typed-audio",
        word: "bank on",
        definition: "To depend on someone.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "typed_recall",
          prompt_token: "prompt-state-typed-audio",
          stem: "Type the word or phrase that matches this definition.",
          question: "To depend on someone.",
          options: null,
          input_mode: "typed",
          audio_state: "ready",
          audio: {
            preferred_playback_url: "/api/words/voice-assets/typed-audio/content",
            preferred_locale: "us",
            locales: {
              us: {
                playback_url: "/api/words/voice-assets/typed-audio/content",
                locale: "en_us",
              },
            },
          },
        },
        detail: {
          entry_type: "phrase",
          entry_id: "phrase-typed-audio",
          display_text: "bank on",
          primary_definition: "To depend on someone.",
          primary_example: "You can bank on her support.",
          meaning_count: 1,
          remembered_count: 0,
          compare_with: [],
          meanings: [],
          audio_state: "ready",
        },
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
    ] as never);

    await renderPage();

    expect(mockPlay).toHaveBeenCalledWith("/api/words/voice-assets/typed-audio/content");
    fireEvent.click(await screen.findByRole("button", { name: /replay audio/i }));
    expect(mockPlay).toHaveBeenCalledTimes(2);
  });

  it("shows an exit-review control during active review and returns home", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-exit",
        queue_item_id: "state-exit",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-exit",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
    ] as never);

    await renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /exit review/i }));
    expect(mockPush).toHaveBeenCalledWith("/");
  });

  it("does not send schedule_override when the learner keeps the default recommendation", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-default",
        queue_item_id: "state-default",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-default",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: {
          entry_type: "word",
          entry_id: "word-default",
          display_text: "barely",
          primary_definition: "Only just, by a very small margin.",
          primary_example: "He barely made it through the door.",
          meaning_count: 1,
          remembered_count: 1,
          compare_with: [],
          meanings: [],
          audio_state: "not_available",
          coverage_summary: "familiar_with_1_meaning",
        },
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
    ] as never);
    mockPost.mockResolvedValue({
      outcome: "correct_tested",
      detail: {
        entry_type: "word",
        entry_id: "word-default",
        display_text: "barely",
        primary_definition: "Only just, by a very small margin.",
        primary_example: "He barely made it through the door.",
        meaning_count: 1,
        remembered_count: 1,
        compare_with: [],
        meanings: [],
        audio_state: "not_available",
        coverage_summary: "familiar_with_1_meaning",
      },
      schedule_options: [
        { value: "1d", label: "Tomorrow", is_default: true },
        { value: "7d", label: "In a week", is_default: false },
      ],
    } as never);

    await renderPage();

    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: /a barely/i }));
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-default/submit",
      expect.not.objectContaining({
        schedule_override: "1d",
      }),
    );
  });

  it("redirects typed correct answers to the real detail page with preview-only submission", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-typed-correct",
        queue_item_id: "state-typed-correct",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "spelling_contrast",
          prompt_token: "prompt-state-typed-correct",
          stem: "Type the exact word or phrase.",
          question: "Only just, by a very small margin.",
          options: null,
          input_mode: "typed",
          expected_input: "barely",
          audio_state: "not_available",
        },
        detail: {
          entry_type: "word",
          entry_id: "word-typed-correct",
          display_text: "barely",
          primary_definition: "Only just, by a very small margin.",
          primary_example: "He barely made it through the door.",
          meaning_count: 1,
          remembered_count: 1,
          compare_with: [],
          meanings: [],
          audio_state: "not_available",
          coverage_summary: "familiar_with_1_meaning",
        },
        schedule_options: [
          { value: "1d", label: "Tomorrow", is_default: true },
          { value: "7d", label: "In a week", is_default: false },
        ],
      },
    ] as never);
    mockPost.mockResolvedValueOnce({
      outcome: "correct_tested",
      detail: {
        entry_type: "word",
        entry_id: "word-typed-correct",
        display_text: "barely",
        primary_definition: "Only just, by a very small margin.",
        primary_example: "He barely made it through the door.",
        meaning_count: 1,
        remembered_count: 1,
        compare_with: [],
        meanings: [],
        audio_state: "not_available",
        coverage_summary: "familiar_with_1_meaning",
      },
      schedule_options: [
        { value: "1d", label: "Tomorrow", is_default: true },
        { value: "7d", label: "In a week", is_default: false },
      ],
    } as never);

    await renderPage();

    fireEvent.change(await screen.findByPlaceholderText(/type the word or phrase/i), {
      target: { value: "barely" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /check answer/i }));
    });

    expect(mockPush).toHaveBeenCalledWith("/word/word-typed-correct?return_to=review&resume=1");
    expect(screen.queryByTestId("review-reveal-state")).not.toBeInTheDocument();

    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-typed-correct/submit",
      expect.objectContaining({
        typed_answer: "barely",
        prompt_token: "prompt-state-typed-correct",
        confirm: false,
      }),
    );
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  it("renders the collocation prompt treatment", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-5",
        queue_item_id: "state-5",
        word: "jump the gun",
        definition: "To do something too soon.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "collocation_check",
          prompt_token: "prompt-state-5",
          stem: "Choose the word or phrase that completes this common expression.",
          question: "They ___ whenever a draft appears.",
          options: [
            { option_id: "A", label: "jump the gun" },
            { option_id: "B", label: "miss the boat" },
          ],
          sentence_masked: "They ___ whenever a draft appears.",
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    await renderPage();

    const prompt = await screen.findByTestId("review-collocation-prompt");
    expect(prompt).toBeInTheDocument();
    expect(prompt).toHaveTextContent(/common expression/i);
    expect(prompt).toHaveTextContent("They ___ whenever a draft appears.");
  });

  it("renders the situation prompt treatment", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-6",
        queue_item_id: "state-6",
        word: "resilience",
        definition: "The capacity to recover quickly from difficulties.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "situation_matching",
          prompt_token: "prompt-state-6",
          stem: "Which word or phrase best fits this situation?",
          question: "___ helps teams adapt after major setbacks.",
          options: [
            { option_id: "A", label: "resilience" },
            { option_id: "B", label: "overreaction" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    await renderPage();

    const prompt = await screen.findByTestId("review-situation-prompt");
    expect(prompt).toBeInTheDocument();
    expect(prompt).toHaveTextContent(/situation/i);
    expect(prompt).toHaveTextContent("___ helps teams adapt after major setbacks.");
  });

  it("renders the speech placeholder treatment with typed fallback", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-7",
        queue_item_id: "state-7",
        word: "resilience",
        definition: "The capacity to recover quickly from difficulties.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "speak_recall",
          prompt_token: "prompt-state-7",
          stem: "Say the word or phrase that matches this definition.",
          question: "The capacity to recover quickly from difficulties.",
          options: null,
          input_mode: "speech_placeholder",
          voice_placeholder_text: "Voice answer coming soon. Type the answer for now.",
          audio_state: "ready",
          audio: {
            preferred_playback_url: "/api/words/voice-assets/speak-audio/content",
            preferred_locale: "us",
            locales: {
              us: {
                playback_url: "/api/words/voice-assets/speak-audio/content",
                locale: "en_us",
              },
            },
          },
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    await renderPage();

    const prompt = await screen.findByTestId("review-speech-placeholder");
    expect(prompt).toBeInTheDocument();
    expect(mockPlay).toHaveBeenCalledWith("/api/words/voice-assets/speak-audio/content");
    expect(prompt).toHaveTextContent(/voice answer coming soon/i);
    expect(screen.getByPlaceholderText(/type the word or phrase/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /replay audio/i }));
    expect(mockPlay).toHaveBeenCalledTimes(2);
  });

  it("renders the confidence check prompt with sentence replay and binary choices", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-confidence",
        queue_item_id: "state-confidence",
        word: "persistence",
        definition: "The ability to keep going despite difficulties.",
        review_mode: "confidence",
        prompt: {
          mode: "confidence",
          prompt_type: "confidence_check",
          prompt_token: "prompt-state-confidence",
          stem: "Read the sentence and decide whether you still remember this word or phrase.",
          question: "Persistence kept the project moving through repeated delays.",
          options: [
            { option_id: "A", label: "I remember it" },
            { option_id: "B", label: "Not sure" },
          ],
          audio_state: "ready",
          audio: {
            preferred_playback_url: "/api/words/voice-assets/confidence-audio/content",
            preferred_locale: "us",
            locales: {
              us: {
                playback_url: "/api/words/voice-assets/confidence-audio/content",
                locale: "en_us",
              },
            },
          },
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    await renderPage();

    expect(mockPlay).toHaveBeenCalledWith("/api/words/voice-assets/confidence-audio/content");
    expect(await screen.findByTestId("review-confidence-prompt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /persistence kept the project moving through repeated delays\./i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /a i remember it/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /b not sure/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /show meaning/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /persistence kept the project moving through repeated delays\./i }));
    expect(mockPlay).toHaveBeenCalledTimes(2);
  });

  it("renders audio prompt controls and replays from the prompt audio payload", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-audio",
        queue_item_id: "state-audio",
        word: "bank",
        definition: "The land alongside a river.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "audio_to_definition",
          prompt_token: "prompt-state-audio",
          stem: "Listen, then choose the best matching definition.",
          question: "Which definition matches the audio?",
          options: [
            { option_id: "A", label: "The land alongside a river." },
            { option_id: "B", label: "A financial institution." },
            { option_id: "C", label: "A pile of snow." },
            { option_id: "D", label: "A mass of cloud." },
          ],
          audio_state: "ready",
          audio: {
            preferred_playback_url: "/api/words/voice-assets/audio-1/content",
            preferred_locale: "us",
            locales: {
              us: {
                playback_url: "/api/words/voice-assets/audio-1/content",
                locale: "en_us",
              },
            },
          },
        },
        detail: {
          entry_type: "word",
          entry_id: "word-audio",
          display_text: "bank",
          primary_definition: "The land alongside a river.",
          primary_example: "We sat on the river bank.",
          meaning_count: 1,
          remembered_count: 0,
          compare_with: [],
          meanings: [],
          audio_state: "ready",
        },
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
    ] as never);
    mockPost.mockResolvedValue({
      outcome: "correct_tested",
      detail: {
        entry_type: "word",
        entry_id: "word-audio",
        display_text: "bank",
        primary_definition: "The land alongside a river.",
        primary_example: "We sat on the river bank.",
        meaning_count: 1,
        remembered_count: 0,
        compare_with: [],
        meanings: [],
        audio_state: "ready",
      },
      schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
    } as never);

    await renderPage();

    expect(mockPlay).toHaveBeenCalledWith("/api/words/voice-assets/audio-1/content");
    expect(screen.queryByText(/^bank$/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /replay audio/i }));
    expect(mockPlay).toHaveBeenCalledTimes(2);
    expect(screen.getAllByRole("button", { name: /^[A-D] /i })).toHaveLength(4);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /a the land alongside a river\./i }));
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-audio/submit",
      expect.objectContaining({
        audio_replay_count: 0,
        selected_option_id: "A",
        prompt_token: "prompt-state-audio",
        confirm: false,
      }),
    );
    expect(mockPush).toHaveBeenCalledWith("/word/word-audio?return_to=review&resume=1");
  });

  it("shows a picture placeholder when pictures in questions is enabled", async () => {
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "us",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
      review_depth_preset: "balanced",
      enable_confidence_check: true,
      enable_word_spelling: true,
      enable_audio_spelling: false,
      show_pictures_in_questions: true,
    });
    mockGet.mockResolvedValue([
      {
        id: "state-picture",
        queue_item_id: "state-picture",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-picture",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    await renderPage();

    expect(await screen.findByTestId("review-picture-placeholder")).toHaveTextContent(/picture hint placeholder/i);
  });

  it("starts phrase learn-now sessions in the learning flow instead of the challenge prompt", async () => {
    window.history.pushState({}, "", "/review?entry_type=phrase&entry_id=phrase-9");
    mockPost
      .mockResolvedValueOnce({
        entry_type: "phrase",
        entry_id: "phrase-9",
        entry_word: "jump the gun",
        meaning_ids: ["sense-9"],
        queue_item_ids: ["state-phrase-9"],
        cards: [
          {
            queue_item_id: "state-phrase-9",
            meaning_id: "sense-9",
            word: "jump the gun",
            definition: "To do something too soon.",
            prompt: {
              mode: "mcq",
              prompt_type: "definition_to_entry",
              prompt_token: "prompt-state-phrase-9",
              stem: "Choose the word or phrase that matches this definition.",
              question: "To do something too soon.",
              options: [
                { option_id: "A", label: "Jump the gun" },
                { option_id: "B", label: "Miss the boat" },
              ],
              audio_state: "not_available",
            },
          },
        ],
        requires_lookup_hint: false,
        detail: {
          entry_type: "phrase",
          entry_id: "phrase-9",
          display_text: "jump the gun",
          primary_definition: "To do something too soon.",
          primary_example: "They jumped the gun and announced it early.",
          meaning_count: 1,
          remembered_count: 0,
          compare_with: [],
          meanings: [
            {
              id: "sense-9",
              definition: "To do something too soon.",
              example: "They jumped the gun and announced it early.",
              part_of_speech: "phrase",
            },
          ],
          audio_state: "not_available",
        },
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      } as never);

    await renderPage();

    await act(async () => {
      await Promise.resolve();
    });
    expect(await screen.findByTestId("review-learning-state")).toBeInTheDocument();
    expect(screen.getByText(/learn 1\/1/i)).toBeInTheDocument();
    expect(screen.getByText("To do something too soon.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /i remember it/i })).not.toBeInTheDocument();

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith("/reviews/entry/phrase/phrase-9/learning/start");
    window.history.pushState({}, "", "/review");
  });

  it("restores the exact review position from session storage when returning from detail", async () => {
    window.history.pushState({}, "", "/review?resume=1");
    window.sessionStorage.setItem(
      "learner-review-session-v1",
      JSON.stringify({
        cards: [
          {
            id: "state-1",
            queue_item_id: "state-1",
            word: "barely",
            definition: "Only just, by a very small margin.",
            review_mode: "mcq",
            prompt: {
              mode: "mcq",
              prompt_type: "definition_to_entry",
              prompt_token: "prompt-state-1",
              stem: "Choose the word or phrase that matches this definition.",
              question: "Only just, by a very small margin.",
              options: [
                { option_id: "A", label: "Barely" },
                { option_id: "B", label: "Bravely" },
              ],
              audio_state: "not_available",
            },
            detail: {
              entry_type: "word",
              entry_id: "word-1",
              display_text: "barely",
              primary_definition: "Only just, by a very small margin.",
              primary_example: "He barely made it through the door.",
              meaning_count: 1,
              remembered_count: 4,
              compare_with: [],
              meanings: [],
              audio_state: "not_available",
            },
            schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
          },
          {
            id: "state-2",
            queue_item_id: "state-2",
            word: "jump the gun",
            definition: "To do something too soon.",
            review_mode: "mcq",
            prompt: {
              mode: "mcq",
              prompt_type: "definition_to_entry",
              prompt_token: "prompt-state-2",
              stem: "Choose the word or phrase that matches this definition.",
              question: "To do something too soon.",
              options: [
                { option_id: "A", label: "Jump the gun" },
                { option_id: "B", label: "Miss the boat" },
              ],
              audio_state: "not_available",
            },
            detail: {
              entry_type: "phrase",
              entry_id: "phrase-2",
              display_text: "jump the gun",
              primary_definition: "To do something too soon.",
              primary_example: "They jumped the gun and announced it early.",
              meaning_count: 1,
              remembered_count: 1,
              compare_with: [],
              meanings: [],
              audio_state: "not_available",
            },
            schedule_options: [{ value: "10m", label: "Later today", is_default: true }],
          },
        ],
        currentIndex: 1,
        phase: "relearn",
        revealState: {
          outcome: "wrong",
          detail: {
            entry_type: "phrase",
            entry_id: "phrase-2",
            display_text: "jump the gun",
            primary_definition: "To do something too soon.",
            primary_example: "They jumped the gun and announced it early.",
            meaning_count: 1,
            remembered_count: 1,
            compare_with: [],
            meanings: [],
            audio_state: "not_available",
          },
          scheduleOptions: [{ value: "10m", label: "Later today", is_default: true }],
          selectedSchedule: "10m",
        },
        typedAnswer: "",
      }),
    );

    await renderPage();

    expect(await screen.findByTestId("review-relearn-state")).toBeInTheDocument();
    expect(screen.getByText(/review 2\/2/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start review/i })).not.toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("loads the due queue immediately when entering /review", async () => {
    mockGet.mockResolvedValue([
      {
        id: "state-1",
        queue_item_id: "state-1",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-1",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
    ] as never);

    await renderPage();

    expect(mockGet).toHaveBeenCalledWith("/reviews/queue/due");
    expect(await screen.findByTestId("review-active-state")).toBeInTheDocument();
    expect(screen.queryByTestId("review-start-button")).not.toBeInTheDocument();
  });

  it("opens a specific due queue item when /review is deep-linked with queue_item_id", async () => {
    window.history.pushState({}, "", "/review?queue_item_id=state-2");
    mockGet.mockResolvedValue([
      {
        id: "state-1",
        queue_item_id: "state-1",
        word: "barely",
        definition: "Only just, by a very small margin.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-1",
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely" },
            { option_id: "B", label: "Bravely" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      },
      {
        id: "state-2",
        queue_item_id: "state-2",
        word: "jump the gun",
        definition: "To do something too soon.",
        review_mode: "mcq",
        prompt: {
          mode: "mcq",
          prompt_type: "definition_to_entry",
          prompt_token: "prompt-state-2",
          stem: "Choose the word or phrase that matches this definition.",
          question: "To do something too soon.",
          options: [
            { option_id: "A", label: "Jump the gun" },
            { option_id: "B", label: "Miss the boat" },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [{ value: "10m", label: "Later today", is_default: true }],
      },
    ] as never);

    await renderPage();

    expect(await screen.findByTestId("review-active-state")).toBeInTheDocument();
    expect(screen.getByText(/review 2\/2/i)).toBeInTheDocument();
    expect(screen.getByText("To do something too soon.")).toBeInTheDocument();
  });
});
