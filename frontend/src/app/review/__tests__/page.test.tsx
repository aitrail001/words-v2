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

describe("ReviewPage", () => {
  const mockGet = apiClient.get as jest.MockedFunction<typeof apiClient.get>;
  const mockPost = apiClient.post as jest.MockedFunction<typeof apiClient.post>;
  const mockUseLearnerAudio = useLearnerAudio as jest.MockedFunction<typeof useLearnerAudio>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockPlay = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    window.sessionStorage.clear();
    window.history.pushState({}, "", "/review");
    mockUseLearnerAudio.mockReturnValue({
      play: mockPlay,
      loadingUrl: null,
      playingUrl: null,
    });
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

  it("shows the reveal step for a correct answer and submits the chosen schedule", async () => {
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
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely", is_correct: true },
            { option_id: "B", label: "Bravely", is_correct: false },
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
    mockPost.mockResolvedValue({} as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));
    fireEvent.click(await screen.findByRole("button", { name: /a barely/i }));

    expect(await screen.findByTestId("review-reveal-state")).toBeInTheDocument();
    expect(screen.getByText("barely")).toBeInTheDocument();
    expect(screen.getByText(/current review depth/i)).toBeInTheDocument();
    expect(screen.getByText(/coverage: deep coverage/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/review in/i), { target: { value: "7d" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-1/submit",
      expect.objectContaining({
        outcome: "correct_tested",
        selected_option_id: "A",
        schedule_override: "7d",
      }),
    );
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
          stem: "Choose the word or phrase that matches this definition.",
          question: "To do something too soon.",
          options: [
            { option_id: "A", label: "Miss the boat", is_correct: false },
            { option_id: "B", label: "Jump the gun", is_correct: true },
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

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));
    fireEvent.click(await screen.findByRole("button", { name: /a miss the boat/i }));

    expect(await screen.findByTestId("review-relearn-state")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open full word details/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/phrase/phrase-1?return_to=review&resume=1"),
    );
    expect(screen.getByText("jump the gun")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-2/submit",
      expect.objectContaining({
        outcome: "wrong",
      }),
    );
  });

  it("shows the reveal step for a correct typed recall answer", async () => {
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
          stem: "Type the word or phrase that matches this definition.",
          question: "To search for information.",
          options: null,
          expected_input: "look up",
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

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));
    fireEvent.change(await screen.findByPlaceholderText(/type the word or phrase/i), {
      target: { value: "  Look, up!! " },
    });
    fireEvent.click(screen.getByRole("button", { name: /check answer/i }));

    expect(await screen.findByTestId("review-reveal-state")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-3/submit",
      expect.objectContaining({
        typed_answer: "  Look, up!! ",
      }),
    );

    const callsBeforeContinue = mockPost.mock.calls.length;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    });
    expect(mockPost.mock.calls).toHaveLength(callsBeforeContinue);
  });

  it("shows the relearn step after a wrong typed recall answer", async () => {
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
          stem: "Type the word or phrase that matches this definition.",
          question: "The capacity to recover quickly from difficulties.",
          options: null,
          expected_input: "resilience",
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
              id: "meaning-4",
              definition: "The capacity to recover quickly from difficulties.",
              example: "Resilience helps teams adapt to change.",
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
            id: "meaning-4",
            definition: "The capacity to recover quickly from difficulties.",
            example: "Resilience helps teams adapt to change.",
          },
        ],
        audio_state: "not_available",
      },
      schedule_options: [{ value: "10m", label: "Later today", is_default: true }],
    } as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));
    fireEvent.change(await screen.findByPlaceholderText(/type the word or phrase/i), {
      target: { value: "reliance" },
    });
    fireEvent.click(screen.getByRole("button", { name: /check answer/i }));

    expect(await screen.findByTestId("review-relearn-state")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-4/submit",
      expect.objectContaining({
        typed_answer: "reliance",
      }),
    );
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
          stem: "Choose the word or phrase that matches this definition.",
          question: "Only just, by a very small margin.",
          options: [
            { option_id: "A", label: "Barely", is_correct: true },
            { option_id: "B", label: "Bravely", is_correct: false },
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
    mockPost.mockResolvedValue({} as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));
    fireEvent.click(await screen.findByRole("button", { name: /a barely/i }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-default/submit",
      expect.not.objectContaining({
        schedule_override: "1d",
      }),
    );
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
          stem: "Choose the word or phrase that completes this common expression.",
          question: "They ___ whenever a draft appears.",
          options: [
            { option_id: "A", label: "jump the gun", is_correct: true },
            { option_id: "B", label: "miss the boat", is_correct: false },
          ],
          sentence_masked: "They ___ whenever a draft appears.",
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));

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
          stem: "Which word or phrase best fits this situation?",
          question: "Resilience helps teams adapt after major setbacks.",
          options: [
            { option_id: "A", label: "resilience", is_correct: true },
            { option_id: "B", label: "overreaction", is_correct: false },
          ],
          audio_state: "not_available",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));

    const prompt = await screen.findByTestId("review-situation-prompt");
    expect(prompt).toBeInTheDocument();
    expect(prompt).toHaveTextContent(/situation/i);
    expect(prompt).toHaveTextContent("Resilience helps teams adapt after major setbacks.");
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
          stem: "Say the word or phrase that matches this definition.",
          question: "The capacity to recover quickly from difficulties.",
          options: null,
          expected_input: "resilience",
          input_mode: "speech_placeholder",
          voice_placeholder_text: "Voice answer coming soon. Type the answer for now.",
          audio_state: "placeholder",
        },
        detail: null,
        schedule_options: [],
      },
    ] as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));

    const prompt = await screen.findByTestId("review-speech-placeholder");
    expect(prompt).toBeInTheDocument();
    expect(prompt).toHaveTextContent(/voice answer coming soon/i);
    expect(screen.getByPlaceholderText(/type the word or phrase/i)).toBeInTheDocument();
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
          stem: "Listen, then choose the best matching definition.",
          question: "bank",
          options: [
            { option_id: "A", label: "The land alongside a river.", is_correct: true },
            { option_id: "B", label: "A financial institution.", is_correct: false },
            { option_id: "C", label: "A pile of snow.", is_correct: false },
            { option_id: "D", label: "A mass of cloud.", is_correct: false },
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

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /start review/i }));

    fireEvent.click(await screen.findByRole("button", { name: /play audio/i }));
    expect(mockPlay).toHaveBeenCalledWith("/api/words/voice-assets/audio-1/content");

    fireEvent.click(screen.getByRole("button", { name: /play again/i }));
    expect(mockPlay).toHaveBeenCalledTimes(2);
    expect(screen.getAllByRole("button", { name: /^[A-D] /i })).toHaveLength(4);

    fireEvent.click(screen.getByRole("button", { name: /a the land alongside a river\./i }));
    expect(await screen.findByTestId("review-reveal-state")).toBeInTheDocument();

    mockPost.mockResolvedValue({} as never);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/queue/state-audio/submit",
      expect.objectContaining({
        audio_replay_count: 1,
      }),
    );
  });

  it("submits phrase learning answers using the entry review state id", async () => {
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
              stem: "Choose the word or phrase that matches this definition.",
              question: "To do something too soon.",
              options: [
                { option_id: "A", label: "Jump the gun", is_correct: true },
                { option_id: "B", label: "Miss the boat", is_correct: false },
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
          meanings: [],
          audio_state: "not_available",
        },
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      } as never)
      .mockResolvedValueOnce({} as never);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /a jump the gun/i }));
    expect(await screen.findByTestId("review-reveal-state")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    });

    expect(mockPost).toHaveBeenNthCalledWith(1, "/reviews/entry/phrase/phrase-9/learning/start");
    expect(mockPost).toHaveBeenNthCalledWith(
      2,
      "/reviews/queue/state-phrase-9/submit",
      expect.objectContaining({
        outcome: "correct_tested",
        selected_option_id: "A",
      }),
    );
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
              stem: "Choose the word or phrase that matches this definition.",
              question: "Only just, by a very small margin.",
              options: [
                { option_id: "A", label: "Barely", is_correct: true },
                { option_id: "B", label: "Bravely", is_correct: false },
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
              stem: "Choose the word or phrase that matches this definition.",
              question: "To do something too soon.",
              options: [
                { option_id: "A", label: "Jump the gun", is_correct: true },
                { option_id: "B", label: "Miss the boat", is_correct: false },
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

    render(<ReviewPage />);

    expect(await screen.findByTestId("review-relearn-state")).toBeInTheDocument();
    expect(screen.getByText(/review 2\/2/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start review/i })).not.toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
