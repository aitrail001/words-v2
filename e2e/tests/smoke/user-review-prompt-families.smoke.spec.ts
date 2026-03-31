import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("@smoke review prompt families render, replay audio, and submit mixed flows", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-families");
  const submitPayloads: Record<string, unknown>[] = [];

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);

  await page.route("**/api/words/voice-assets/*/content", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "fixture-audio",
    });
  });

  await page.route("**/api/knowledge-map/entries/word/word-situation*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entry_type: "word",
        entry_id: "word-situation",
        display_text: "resilience",
        normalized_form: "resilience",
        browse_rank: 20,
        status: "learning",
        cefr_level: "B2",
        pronunciation: "/rɪˈzɪliəns/",
        translation: "resiliencia",
        primary_definition: "The capacity to recover quickly from difficulties.",
        voice_assets: [
          {
            id: "voice-resilience-us",
            content_scope: "word",
            locale: "en_us",
            playback_url: "/api/words/voice-assets/voice-resilience-us/content",
          },
          {
            id: "voice-resilience-definition-us",
            content_scope: "definition",
            locale: "en_us",
            meaning_id: "meaning-situation",
            playback_url: "/api/words/voice-assets/voice-resilience-definition-us/content",
          },
          {
            id: "voice-resilience-example-us",
            content_scope: "example",
            locale: "en_us",
            meaning_example_id: "example-situation",
            playback_url: "/api/words/voice-assets/voice-resilience-example-us/content",
          },
        ],
        meanings: [
          {
            id: "meaning-situation",
            definition: "The capacity to recover quickly from difficulties.",
            localized_definition: "resiliencia",
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
                id: "example-situation",
                sentence: "Resilience helps teams adapt after major setbacks.",
                difficulty: "B2",
                translation: "La resiliencia ayuda a los equipos a adaptarse tras grandes contratiempos.",
              },
            ],
            translations: [{ id: "translation-situation", language: "es", translation: "resiliencia" }],
            relations: [],
          },
        ],
        senses: [],
        relation_groups: [],
        confusable_words: [],
        previous_entry: null,
        next_entry: null,
      }),
    });
  });

  await page.route("**/api/reviews/queue/due**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "state-audio",
          queue_item_id: "state-audio",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "audio_to_definition",
            stem: "Listen and choose the matching meaning.",
            question: "Which definition matches the audio?",
            options: [
              { option_id: "A", label: "The capacity to recover quickly from difficulties.", is_correct: true },
              { option_id: "B", label: "A severe reaction to small changes.", is_correct: false },
              { option_id: "C", label: "A habit of avoiding effort.", is_correct: false },
              { option_id: "D", label: "A formal request for help.", is_correct: false },
            ],
            audio_state: "ready",
            audio: {
              preferred_locale: "us",
              preferred_playback_url: "/api/words/voice-assets/review-audio/content",
              locales: {
                us: {
                  playback_url: "/api/words/voice-assets/review-audio/content",
                  locale: "en_us",
                  relative_path: "learner/resilience/word/en_us.mp3",
                },
              },
            },
          },
          detail: {
            entry_type: "word",
            entry_id: "word-audio",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt after major setbacks.",
            meaning_count: 1,
            remembered_count: 1,
            compare_with: [],
            meanings: [],
            audio_state: "ready",
          },
          schedule_options: [{ value: "2d", label: "In 2 days", is_default: true }],
        },
        {
          id: "state-collocation",
          queue_item_id: "state-collocation",
          word: "jump the gun",
          definition: "To do something too soon.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "collocation_check",
            stem: "Choose the common expression that best fits the sentence.",
            question: "They ___ and announced it early.",
            sentence_masked: "They ___ and announced it early.",
            options: [
              { option_id: "A", label: "jump the gun", is_correct: true },
              { option_id: "B", label: "miss the boat", is_correct: false },
              { option_id: "C", label: "cut corners", is_correct: false },
              { option_id: "D", label: "take over", is_correct: false },
            ],
            audio_state: "not_available",
          },
          detail: {
            entry_type: "phrase",
            entry_id: "phrase-collocation",
            display_text: "jump the gun",
            primary_definition: "To do something too soon.",
            primary_example: "They jumped the gun and announced it early.",
            meaning_count: 1,
            remembered_count: 2,
            compare_with: ["move too fast"],
            meanings: [],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "3d", label: "In 3 days", is_default: true }],
        },
        {
          id: "state-situation",
          queue_item_id: "state-situation",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "situation_matching",
            stem: "Which word or phrase best fits this situation?",
            question: "A team keeps adapting after repeated setbacks.",
            options: [
              { option_id: "A", label: "overreaction", is_correct: false },
              { option_id: "B", label: "resilience", is_correct: true },
              { option_id: "C", label: "avoidance", is_correct: false },
              { option_id: "D", label: "confusion", is_correct: false },
            ],
            audio_state: "not_available",
          },
          detail: {
            entry_type: "word",
            entry_id: "word-situation",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt after major setbacks.",
            meaning_count: 1,
            remembered_count: 3,
            compare_with: [],
            meanings: [
              {
                id: "meaning-situation",
                definition: "The capacity to recover quickly from difficulties.",
                example: "Resilience helps teams adapt after major setbacks.",
              },
            ],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        },
        {
          id: "state-speak",
          queue_item_id: "state-speak",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "speak_recall",
            stem: "Say or type the word or phrase that matches this definition.",
            question: "The capacity to recover quickly from difficulties.",
            options: null,
            expected_input: "resilience",
            input_mode: "speech_placeholder",
            voice_placeholder_text: "Voice capture is not live yet. Type the answer for now.",
            audio_state: "placeholder",
          },
          detail: {
            entry_type: "word",
            entry_id: "word-speak",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt to change.",
            meaning_count: 1,
            remembered_count: 4,
            compare_with: [],
            meanings: [],
            audio_state: "placeholder",
          },
          schedule_options: [{ value: "7d", label: "In a week", is_default: true }],
        },
      ]),
    });
  });

  await page.route("**/api/reviews/queue/*/submit", async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    submitPayloads.push(payload);

    const itemId = route.request().url().split("/").pop() ?? "";
    if (payload.outcome === "wrong" && itemId === "state-situation") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            entry_type: "word",
            entry_id: "word-situation",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt after major setbacks.",
            meaning_count: 1,
            remembered_count: 3,
            compare_with: [],
            meanings: [
              {
                id: "meaning-situation",
                definition: "The capacity to recover quickly from difficulties.",
                example: "Resilience helps teams adapt after major setbacks.",
              },
            ],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });

  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();

  await expect(page.getByRole("button", { name: /play audio/i })).toBeVisible();
  await page.getByRole("button", { name: /play audio/i }).click();
  await expect(page.getByRole("button", { name: /play again/i })).toBeVisible();
  await page.getByRole("button", { name: /the capacity to recover quickly from difficulties/i }).click();
  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-collocation-prompt")).toBeVisible();
  await expect(page.getByTestId("review-collocation-prompt").getByText(/common expression/i)).toBeVisible();
  await page.getByRole("button", { name: /jump the gun/i }).click();
  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-situation-prompt")).toBeVisible();
  await expect(
    page.getByTestId("review-situation-prompt").getByText(
      /a team keeps adapting after repeated setbacks/i,
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: /overreaction/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await expect(page.getByRole("link", { name: /open full word details/i })).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-speech-placeholder")).toBeVisible();
  await expect(page.getByText(/voice capture is not live yet/i)).toBeVisible();
  await page.getByPlaceholder(/type the word or phrase/i).fill("resilience");
  await page.getByRole("button", { name: /check answer/i }).click();
  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-complete-state")).toBeVisible();
  await expect(page.getByText(/you reviewed 4 entries/i)).toBeVisible();

  expect(submitPayloads).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        outcome: "correct_tested",
        selected_option_id: "A",
        schedule_override: "2d",
      }),
      expect.objectContaining({
        outcome: "correct_tested",
        selected_option_id: "A",
        schedule_override: "3d",
      }),
      expect.objectContaining({
        outcome: "wrong",
      }),
      expect.objectContaining({
        outcome: "correct_tested",
        typed_answer: "resilience",
        schedule_override: "7d",
      }),
    ]),
  );
});

test("@smoke review relearn opens the full detail page with learner audio controls", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-relearn-detail");

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);

  await page.route("**/api/words/voice-assets/*/content", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "fixture-audio",
    });
  });

  await page.route("**/api/knowledge-map/entries/word/word-situation*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entry_type: "word",
        entry_id: "word-situation",
        display_text: "resilience",
        normalized_form: "resilience",
        browse_rank: 20,
        status: "learning",
        cefr_level: "B2",
        pronunciation: "/rɪˈzɪliəns/",
        translation: "resiliencia",
        primary_definition: "The capacity to recover quickly from difficulties.",
        voice_assets: [
          {
            id: "voice-resilience-us",
            content_scope: "word",
            locale: "en_us",
            playback_url: "/api/words/voice-assets/voice-resilience-us/content",
          },
          {
            id: "voice-resilience-definition-us",
            content_scope: "definition",
            locale: "en_us",
            meaning_id: "meaning-situation",
            playback_url: "/api/words/voice-assets/voice-resilience-definition-us/content",
          },
          {
            id: "voice-resilience-example-us",
            content_scope: "example",
            locale: "en_us",
            meaning_example_id: "example-situation",
            playback_url: "/api/words/voice-assets/voice-resilience-example-us/content",
          },
        ],
        meanings: [
          {
            id: "meaning-situation",
            definition: "The capacity to recover quickly from difficulties.",
            localized_definition: "resiliencia",
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
                id: "example-situation",
                sentence: "Resilience helps teams adapt after major setbacks.",
                difficulty: "B2",
                translation: "La resiliencia ayuda a los equipos a adaptarse tras grandes contratiempos.",
              },
            ],
            translations: [{ id: "translation-situation", language: "es", translation: "resiliencia" }],
            relations: [],
          },
        ],
        senses: [],
        relation_groups: [],
        confusable_words: [],
        previous_entry: null,
        next_entry: null,
      }),
    });
  });

  await page.route("**/api/reviews/queue/due**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "state-situation",
          queue_item_id: "state-situation",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "situation_matching",
            stem: "Which word or phrase best fits this situation?",
            question: "A team keeps adapting after repeated setbacks.",
            options: [
              { option_id: "A", label: "overreaction", is_correct: false },
              { option_id: "B", label: "resilience", is_correct: true },
              { option_id: "C", label: "avoidance", is_correct: false },
              { option_id: "D", label: "confusion", is_correct: false },
            ],
            audio_state: "not_available",
          },
          detail: {
            entry_type: "word",
            entry_id: "word-situation",
            display_text: "resilience",
            primary_definition: "The capacity to recover quickly from difficulties.",
            primary_example: "Resilience helps teams adapt after major setbacks.",
            meaning_count: 1,
            remembered_count: 3,
            compare_with: [],
            meanings: [
              {
                id: "meaning-situation",
                definition: "The capacity to recover quickly from difficulties.",
                example: "Resilience helps teams adapt after major setbacks.",
              },
            ],
            audio_state: "not_available",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        },
      ]),
    });
  });

  await page.route("**/api/reviews/queue/*/submit", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          entry_type: "word",
          entry_id: "word-situation",
          display_text: "resilience",
          primary_definition: "The capacity to recover quickly from difficulties.",
          primary_example: "Resilience helps teams adapt after major setbacks.",
          meaning_count: 1,
          remembered_count: 3,
          compare_with: [],
          meanings: [
            {
              id: "meaning-situation",
              definition: "The capacity to recover quickly from difficulties.",
              example: "Resilience helps teams adapt after major setbacks.",
            },
          ],
          audio_state: "not_available",
        },
        schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
      }),
    });
  });

  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();
  await page.getByRole("button", { name: /overreaction/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await page.getByRole("link", { name: /open full word details/i }).click();

  await expect(page).toHaveURL(/\/word\/word-situation\?return_to=review&resume=1$/);
  await expect(page.getByRole("button", { name: /back to review/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /play audio for resilience/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /play definition audio for resilience/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /play example audio for resilience/i })).toBeVisible();
  await page.getByRole("button", { name: /back to review/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await expect(page.getByRole("heading", { name: "resilience" })).toBeVisible();
});
