import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("@smoke confidence-check prompts replay audio and honor picture placeholders", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-confidence");
  const requestedAudioUrls: string[] = [];

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);

  await page.route("**/api/user-preferences", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        accent_preference: "us",
        translation_locale: "es",
        knowledge_view_preference: "cards",
        show_translations_by_default: true,
        review_depth_preset: "balanced",
        enable_confidence_check: true,
        enable_word_spelling: true,
        enable_audio_spelling: false,
        show_pictures_in_questions: true,
      }),
    });
  });

  await page.route("**/api/words/voice-assets/*/content", async (route) => {
    requestedAudioUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "fixture-audio",
    });
  });

  await page.route("**/api/reviews/queue/due", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
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
              preferred_locale: "us",
              preferred_playback_url: "/api/words/voice-assets/confidence-audio/content",
              locales: {
                us: {
                  playback_url: "/api/words/voice-assets/confidence-audio/content",
                  locale: "en_us",
                },
              },
            },
          },
          detail: {
            entry_type: "word",
            entry_id: "word-confidence",
            display_text: "persistence",
            primary_definition: "The ability to keep going despite difficulties.",
            primary_example: "Persistence kept the project moving through repeated delays.",
            meaning_count: 1,
            remembered_count: 1,
            compare_with: [],
            meanings: [
              {
                id: "meaning-confidence",
                definition: "The ability to keep going despite difficulties.",
                example: "Persistence kept the project moving through repeated delays.",
                part_of_speech: "noun",
              },
            ],
            audio_state: "ready",
            coverage_summary: "familiar_with_1_meaning",
          },
          schedule_options: [{ value: "1d", label: "Tomorrow", is_default: true }],
        },
      ]),
    });
  });

  await page.route("**/api/reviews/queue/state-confidence/submit", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        outcome: "wrong",
        detail: {
          entry_type: "word",
          entry_id: "word-confidence",
          display_text: "persistence",
          primary_definition: "The ability to keep going despite difficulties.",
          primary_example: "Persistence kept the project moving through repeated delays.",
          meaning_count: 1,
          remembered_count: 1,
          compare_with: [],
          meanings: [
            {
              id: "meaning-confidence",
              definition: "The ability to keep going despite difficulties.",
              example: "Persistence kept the project moving through repeated delays.",
              part_of_speech: "noun",
            },
          ],
          audio_state: "ready",
          coverage_summary: "familiar_with_1_meaning",
        },
        schedule_options: [{ value: "10m", label: "Later today", is_default: true }],
      }),
    });
  });

  await page.goto("/review");

  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await expect(page.getByTestId("review-confidence-prompt")).toBeVisible();
  await expect(page.getByTestId("review-picture-placeholder")).toBeVisible();
  await expect(page.getByRole("button", { name: /show meaning/i })).toHaveCount(0);

  await page.getByRole("button", { name: /persistence kept the project moving through repeated delays\./i }).click();
  await page.getByRole("button", { name: /not sure/i }).click();

  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  expect(requestedAudioUrls).toContainEqual(expect.stringContaining("/api/words/voice-assets/confidence-audio/content"));
});
