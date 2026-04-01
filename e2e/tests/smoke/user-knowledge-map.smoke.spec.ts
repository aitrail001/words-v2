import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import {
  LEARN_WORD,
  KNOWLEDGE_PHRASE,
  KNOWLEDGE_WORD,
  seedKnowledgeMapFixture,
} from "../helpers/knowledge-map-fixture";

test("@smoke learner knowledge map supports mixed catalog browsing and persisted statuses", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const user = await registerViaApi(request, "knowledge-map");
  const fixture = await seedKnowledgeMapFixture(user.id);
  const requestedAudioUrls: string[] = [];

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });
  await page.route("**/api/words/voice-assets/*/content", async (route) => {
    requestedAudioUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "audio/mpeg",
      body: "fixture-audio",
    });
  });
  await page.route(`**/api/knowledge-map/entries/word/${fixture.wordId}*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entry_type: "word",
        entry_id: fixture.wordId,
        display_text: KNOWLEDGE_WORD,
        normalized_form: KNOWLEDGE_WORD,
        browse_rank: 20,
        status: "known",
        cefr_level: null,
        pronunciation: "/rɪˈzɪliəns/",
        pronunciations: {
          us: "/rɪˈzɪliəns/",
          uk: "/rɪˈzɪl.i.əns/",
        },
        translation: "resiliencia",
        primary_definition: "The ability to recover quickly from setbacks.",
        voice_assets: [
          {
            id: "voice-word-us",
            content_scope: "word",
            locale: "en_us",
            playback_url: "/api/words/voice-assets/voice-word-us/content",
          },
          {
            id: "voice-word-uk",
            content_scope: "word",
            locale: "en_gb",
            playback_url: "/api/words/voice-assets/voice-word-uk/content",
          },
          {
            id: "voice-definition-us",
            content_scope: "definition",
            locale: "en_us",
            meaning_id: "meaning-1",
            playback_url: "/api/words/voice-assets/voice-definition-us/content",
          },
          {
            id: "voice-example-us",
            content_scope: "example",
            locale: "en_us",
            meaning_example_id: "example-1",
            playback_url: "/api/words/voice-assets/voice-example-us/content",
          },
        ],
        meanings: [
          {
            id: "meaning-1",
            definition: "The ability to recover quickly from setbacks.",
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
                id: "example-1",
                sentence: "Resilience helps teams adapt to sudden change.",
                difficulty: "B2",
                translation: "La resiliencia ayuda a los equipos a adaptarse al cambio repentino.",
                linked_entries: [],
              },
            ],
            translations: [{ id: "translation-1", language: "es", translation: "resiliencia" }],
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

  await injectToken(page, user.token);

  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Knowledge Map" })).toBeVisible();
  await expect(page.getByRole("link", { name: /knew/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /started/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /to learn/i })).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /started/i }).click();
  await expect(page).toHaveURL(/\/knowledge-list\/learning$/);
  await expect(page.getByRole("heading", { name: "Learning Words" })).toBeVisible();
  await expect(page.getByText(KNOWLEDGE_PHRASE, { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Alphabetic" })).toBeVisible();
  await page.getByRole("button", { name: "Alphabetic" }).click();
  await expect(page.getByRole("button", { name: "Hardest First" })).toBeVisible();
  await page.getByRole("button", { name: "Hardest First" }).click();
  await expect(page.getByRole("button", { name: "Easiest First" })).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /to learn/i }).click();
  await expect(page).toHaveURL(/\/knowledge-list\/to-learn$/);
  await expect(page.getByRole("heading", { name: "To Learn" })).toBeVisible();
  await expect(page.getByText(LEARN_WORD, { exact: false })).toBeVisible();

  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Search" })).toBeVisible();
  await page.getByPlaceholder("Search words and phrases").fill("bank");
  const phraseResult = page.getByRole("link", { name: new RegExp(KNOWLEDGE_PHRASE, "i") });
  await expect(phraseResult).toBeVisible();
  await phraseResult.click();

  await expect(page).toHaveURL(new RegExp(`/phrase/${fixture.phraseId}$`));
  await expect(page.getByRole("heading", { name: KNOWLEDGE_PHRASE })).toBeVisible();
  await expect(page.getByText("depender de").first()).toBeVisible();
  await expect(page.getByText("You can bank on me when the deadline gets tight.").first()).toBeVisible();
  await expect(page.getByText("Puedes depender de mi cuando el plazo es corto.")).toBeVisible();
  await expect(page.getByText("Investors bank on steady demand in the winter season.")).toBeVisible();
  await expect(
    page.getByText("Los inversores dependen de una demanda estable en la temporada de invierno."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /spanish on/i })).toBeVisible();
  await expect(page.getByText("Status: Learning")).toBeVisible();

  await page.getByRole("button", { name: "Known" }).click();
  await expect(page.getByText("Status: Known")).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /discover/i }).click();
  await expect(page).toHaveURL(/\/knowledge-map/);
  await expect(page.getByRole("heading", { name: "Full Knowledge Map" })).toBeVisible();
  const firstRangeLink = page.getByRole("link", { name: "1-100", exact: true });
  await expect(firstRangeLink).toBeVisible();
  await firstRangeLink.click();
  await expect(page).toHaveURL(/\/knowledge-map\/range\/1$/);
  await expect(page.getByRole("heading", { name: /range [\d,]+\s*-\s*[\d,]+/i })).toBeVisible();
  await page.getByRole("button", { name: "Cards view" }).click();
  await expect(page.getByRole("button", { name: `Play audio for ${KNOWLEDGE_WORD}` })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use US accent" }).first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByText("/rɪˈzɪliəns/")).toBeVisible();
  await page.getByRole("button", { name: `Play audio for ${KNOWLEDGE_WORD}` }).click();
  await expect
    .poll(() => requestedAudioUrls.at(-1))
    .toContain("/api/words/voice-assets/");
  await page.getByRole("button", { name: "Use UK accent" }).first().click();
  await expect(page.getByRole("button", { name: "Use UK accent" }).first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByText("/rɪˈzɪl.i.əns/")).toBeVisible();

  await page.goto("/");
  const learnNextLink = page.getByRole("link", { name: /learn next:/i });
  await expect(learnNextLink).toBeVisible({ timeout: 30000 });
  await learnNextLink.click();
  await expect(page).toHaveURL(new RegExp(`/word/${fixture.learnWordId}$`));
  await expect(page.getByRole("heading", { name: LEARN_WORD })).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("tambor").first()).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("button", { name: `Play audio for ${LEARN_WORD}` })).toBeVisible();
  await expect(page.getByRole("button", { name: `Play definition audio for ${LEARN_WORD}` })).toBeVisible();
  await expect(page.getByRole("button", { name: `Play example audio for ${LEARN_WORD}` })).toBeVisible();
  await page.getByRole("button", { name: `Play audio for ${LEARN_WORD}` }).click();
  await page.getByRole("button", { name: `Play definition audio for ${LEARN_WORD}` }).click();
  await page.getByRole("button", { name: `Play example audio for ${LEARN_WORD}` }).click();
  await expect.poll(() => requestedAudioUrls.length).toBeGreaterThanOrEqual(3);

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText("Learning")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Translation" })).toBeVisible();
  await page.getByRole("button", { name: /show translations by default/i }).click();
  await expect(page.getByRole("button", { name: /show translations by default/i })).toContainText("Off");

  await page.goto(`/word/${fixture.wordId}`);
  await expect(page.getByRole("heading", { name: KNOWLEDGE_WORD })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use US accent" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("/rɪˈzɪliəns/")).toBeVisible();
  await expect(page.getByRole("button", { name: `Play audio for ${KNOWLEDGE_WORD}` })).toBeVisible();
  await expect(page.getByRole("button", { name: `Play definition audio for ${KNOWLEDGE_WORD}` })).toBeVisible();
  await expect(page.getByRole("button", { name: `Play example audio for ${KNOWLEDGE_WORD}` })).toBeVisible();

  await page.getByRole("button", { name: `Play audio for ${KNOWLEDGE_WORD}` }).click();
  await expect
    .poll(() => requestedAudioUrls.at(-1))
    .toContain("/api/words/voice-assets/");

  await page.getByRole("button", { name: "Use UK accent" }).click();
  await expect(page.getByRole("button", { name: "Use UK accent" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("/rɪˈzɪl.i.əns/")).toBeVisible();
  await page.getByRole("button", { name: `Play definition audio for ${KNOWLEDGE_WORD}` }).click();
  await page.getByRole("button", { name: `Play example audio for ${KNOWLEDGE_WORD}` }).click();
  await expect.poll(() => requestedAudioUrls.length).toBeGreaterThanOrEqual(3);

  await page.goto("/search");
  await page.getByPlaceholder("Search words and phrases").fill("drum");
  await expect(page.getByText("tambor")).toHaveCount(0);
});
