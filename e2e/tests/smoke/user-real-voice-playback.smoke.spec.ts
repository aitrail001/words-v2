import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import {
  ensureRealVoiceFixture,
  REAL_PHRASE_TEXT,
  REAL_WORD_TEXT,
} from "../helpers/real-voice-fixture";

test("@smoke real local voice assets play through authenticated detail and review flows", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "real-voice-playback");
  const fixture = await ensureRealVoiceFixture();

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);

  await page.route(`**/api/knowledge-map/entries/word/${fixture.wordId}*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entry_type: "word",
        entry_id: fixture.wordId,
        display_text: REAL_WORD_TEXT,
        normalized_form: REAL_WORD_TEXT,
        browse_rank: 42,
        status: "learning",
        cefr_level: "B1",
        pronunciation: "/əˈbɪl.ə.ti/",
        pronunciations: {
          us: "/əˈbɪləti/",
          uk: "/əˈbɪl.ə.ti/",
        },
        translation: "habilidad",
        primary_definition: "The power or skill needed to do something.",
        voice_assets: [
          {
            id: fixture.wordVoiceUsId,
            content_scope: "word",
            locale: "en-US",
            playback_url: `/api/words/voice-assets/${fixture.wordVoiceUsId}/content`,
          },
          {
            id: fixture.wordVoiceUkId,
            content_scope: "word",
            locale: "en-GB",
            playback_url: `/api/words/voice-assets/${fixture.wordVoiceUkId}/content`,
          },
        ],
        meanings: [
          {
            id: "real-word-meaning-1",
            definition: "The power or skill needed to do something.",
            localized_definition: "habilidad",
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
            translations: [{ id: "real-word-translation-1", language: "es", translation: "habilidad" }],
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

  await page.route(`**/api/knowledge-map/entries/phrase/${fixture.phraseId}*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entry_type: "phrase",
        entry_id: fixture.phraseId,
        display_text: REAL_PHRASE_TEXT,
        normalized_form: REAL_PHRASE_TEXT,
        browse_rank: 314,
        status: "learning",
        cefr_level: "B2",
        pronunciation: null,
        translation: "una bendición disfrazada",
        primary_definition: "Something that seems bad at first but later turns out to be good.",
        voice_assets: [
          {
            id: fixture.phraseVoiceUsId,
            content_scope: "word",
            locale: "en-US",
            playback_url: `/api/words/voice-assets/${fixture.phraseVoiceUsId}/content`,
          },
          {
            id: fixture.phraseVoiceUkId,
            content_scope: "word",
            locale: "en-GB",
            playback_url: `/api/words/voice-assets/${fixture.phraseVoiceUkId}/content`,
          },
        ],
        meanings: [],
        senses: [
          {
            id: "real-phrase-sense-1",
            definition: "Something that seems bad at first but later turns out to be good.",
            localized_definition: "una bendición disfrazada",
            part_of_speech: "idiom",
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
            translations: [],
            relations: [],
          },
        ],
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
          id: "real-audio-review",
          queue_item_id: "real-audio-review",
          word: REAL_WORD_TEXT,
          definition: "The power or skill needed to do something.",
          review_mode: "mcq",
          prompt: {
            mode: "mcq",
            prompt_type: "audio_to_definition",
            prompt_token: "prompt-real-audio-review",
            stem: "Listen and choose the matching meaning.",
            question: "Which definition matches the audio?",
            options: [
              { option_id: "A", label: "The power or skill needed to do something." },
              { option_id: "B", label: "A container for money." },
              { option_id: "C", label: "A surprising good outcome after trouble." },
            ],
            audio_state: "ready",
            audio: {
              preferred_locale: "us",
              preferred_playback_url: `/api/words/voice-assets/${fixture.wordVoiceUsId}/content`,
              locales: {
                us: {
                  playback_url: `/api/words/voice-assets/${fixture.wordVoiceUsId}/content`,
                  locale: "en_us",
                },
              },
            },
          },
          detail: {
            entry_type: "word",
            entry_id: fixture.wordId,
            display_text: REAL_WORD_TEXT,
            primary_definition: "The power or skill needed to do something.",
            primary_example: "She has the ability to stay calm under pressure.",
            meaning_count: 1,
            remembered_count: 1,
            compare_with: [],
            meanings: [],
            audio_state: "ready",
            coverage_summary: "familiar_with_1_meaning",
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
      body: JSON.stringify({}),
    });
  });

  await page.goto(`/word/${fixture.wordId}`);
  await expect(page.getByRole("button", { name: /play audio for ability/i })).toBeVisible();
  const wordResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/words/voice-assets/${fixture.wordVoiceUkId}/content`) &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Use UK accent" }).click();
  await page.getByRole("button", { name: /play audio for ability/i }).click();
  const wordResponse = await wordResponsePromise;
  expect(wordResponse.headers()["content-type"]).toContain("audio/mpeg");

  await page.goto(`/phrase/${fixture.phraseId}`);
  await expect(page.getByRole("button", { name: /play audio for a blessing in disguise/i })).toBeVisible();
  const phraseResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/words/voice-assets/${fixture.phraseVoiceUsId}/content`) &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Use US accent" }).click();
  await page.getByRole("button", { name: /play audio for a blessing in disguise/i }).click();
  const phraseResponse = await phraseResponsePromise;
  expect(phraseResponse.headers()["content-type"]).toContain("audio/mpeg");

  await page.goto("/review");
  await page.getByRole("button", { name: /start review/i }).click();
  await expect(page.getByRole("button", { name: /play audio/i })).toBeVisible();
  const reviewResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/words/voice-assets/${fixture.wordVoiceUsId}/content`) &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: /play audio/i }).click();
  const reviewResponse = await reviewResponsePromise;
  expect(reviewResponse.headers()["content-type"]).toContain("audio/mpeg");
});
