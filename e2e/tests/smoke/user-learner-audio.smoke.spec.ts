import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("@smoke learner audio covers range cards and review replay", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "learner-audio");
  const requestedAudioUrls: string[] = [];
  const submitPayloads: Record<string, unknown>[] = [];

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);

  await page.route("**/api/words/voice-assets/*/content", async (route) => {
    requestedAudioUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "fixture-audio",
    });
  });

  await page.route("**/api/knowledge-map/ranges/1*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        range_start: 1,
        range_end: 100,
        previous_range_start: null,
        next_range_start: null,
        items: [
          {
            entry_type: "word",
            entry_id: "word-audio",
            display_text: "resilience",
            normalized_form: "resilience",
            browse_rank: 20,
            status: "learning",
            cefr_level: "B2",
            pronunciation: "/rɪˈzɪl.i.əns/",
            pronunciations: {
              us: "/rɪˈzɪliəns/",
              uk: "/rɪˈzɪl.i.əns/",
            },
            translation: "resiliencia",
            primary_definition: "The capacity to recover quickly from difficulties.",
            part_of_speech: "noun",
            phrase_kind: null,
            voice_assets: [
              {
                id: "voice-word-us",
                content_scope: "word",
                locale: "en-US",
                playback_url: "/api/words/voice-assets/voice-word-us/content",
              },
              {
                id: "voice-word-uk",
                content_scope: "word",
                locale: "en-GB",
                playback_url: "/api/words/voice-assets/voice-word-uk/content",
              },
            ],
          },
        ],
      }),
    });
  });

  await page.route("**/api/knowledge-map/entries/**", async (route) => {
    const url = route.request().url();
    const isWordAudio = url.includes("/word-audio");
    const entryId = isWordAudio ? "word-audio" : "word-situation";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entry_type: "word",
        entry_id: entryId,
        display_text: "resilience",
        normalized_form: "resilience",
        browse_rank: 20,
        status: "learning",
        cefr_level: "B2",
        pronunciation: "/rɪˈzɪl.i.əns/",
        pronunciations: {
          us: "/rɪˈzɪliəns/",
          uk: "/rɪˈzɪl.i.əns/",
        },
        translation: "resiliencia",
        primary_definition: "The capacity to recover quickly from difficulties.",
        voice_assets: [
          {
            id: "voice-resilience-us",
            content_scope: "word",
            locale: "en-US",
            playback_url: "/api/words/voice-assets/voice-resilience-us/content",
          },
          {
            id: "voice-resilience-uk",
            content_scope: "word",
            locale: "en-GB",
            playback_url: "/api/words/voice-assets/voice-resilience-uk/content",
          },
          {
            id: "voice-resilience-definition-us",
            content_scope: "definition",
            locale: "en-US",
            meaning_id: "meaning-situation",
            playback_url: "/api/words/voice-assets/voice-resilience-definition-us/content",
          },
          {
            id: "voice-resilience-example-us",
            content_scope: "example",
            locale: "en-US",
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
            prompt_token: "prompt-state-audio",
            stem: "Listen and choose the matching meaning.",
            question: "Which definition matches the audio?",
            options: [
              { option_id: "A", label: "The capacity to recover quickly from difficulties." },
              { option_id: "B", label: "A severe reaction to small changes." },
              { option_id: "C", label: "A habit of avoiding effort." },
              { option_id: "D", label: "A formal request for help." },
            ],
            audio_state: "ready",
            audio: {
              preferred_locale: "us",
              preferred_playback_url: "/api/words/voice-assets/review-audio/content",
              locales: {
                us: {
                  playback_url: "/api/words/voice-assets/review-audio/content",
                  locale: "en_us",
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
          id: "state-situation",
          queue_item_id: "state-situation",
          word: "resilience",
          definition: "The capacity to recover quickly from difficulties.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "situation_matching",
            prompt_token: "prompt-state-situation",
            stem: "Which word or phrase best fits this situation?",
            question: "A team keeps adapting after repeated setbacks.",
            options: [
              { option_id: "A", label: "overreaction" },
              { option_id: "B", label: "resilience" },
              { option_id: "C", label: "avoidance" },
              { option_id: "D", label: "confusion" },
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
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    submitPayloads.push(payload);
    const urlSegments = route.request().url().split("/");
    const itemId = urlSegments[urlSegments.length - 2] ?? "";

    if (itemId === "state-audio" && payload.selected_option_id === "A") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          outcome: "correct_tested",
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
        }),
      });
      return;
    }
    if (itemId === "state-situation") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          outcome: "wrong",
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

  await page.goto("/knowledge-map/range/1");
  await expect(page.getByRole("heading", { name: /range 1-100/i })).toBeVisible();
  await page.getByRole("button", { name: "Cards view" }).click();
  await expect(page.getByRole("button", { name: /play audio for resilience/i })).toBeVisible();
  await page.getByRole("button", { name: "Use UK accent" }).click();
  await expect(page.getByRole("button", { name: "Use UK accent" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("/rɪˈzɪl.i.əns/")).toBeVisible();
  await page.getByRole("button", { name: /play audio for resilience/i }).click();
  await expect.poll(() => requestedAudioUrls.at(-1)).toContain("/api/words/voice-assets/");
  await page.getByRole("button", { name: "Use US accent" }).click();
  await expect(page.getByRole("button", { name: "Use US accent" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("/rɪˈzɪliəns/")).toBeVisible();

  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();
  await expect(page.getByRole("button", { name: /play audio/i })).toBeVisible();
  await page.getByRole("button", { name: /play audio/i }).click();
  await expect(page.getByRole("button", { name: /play again/i })).toBeVisible();
  await page.getByRole("button", { name: /the capacity to recover quickly from difficulties/i }).click();
  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-situation-prompt")).toBeVisible();
  await page.getByRole("button", { name: /overreaction/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await expect(page.getByRole("heading", { name: "resilience" })).toBeVisible();

  expect(submitPayloads).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        selected_option_id: "A",
        prompt_token: "prompt-state-audio",
      }),
      expect.objectContaining({
        outcome: "correct_tested",
        selected_option_id: "A",
        prompt_token: "prompt-state-audio",
      }),
      expect.objectContaining({
        selected_option_id: "A",
        prompt_token: "prompt-state-situation",
      }),
    ]),
  );
});
