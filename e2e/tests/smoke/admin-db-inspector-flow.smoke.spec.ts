import { expect, test } from "@playwright/test";
import { Client } from "pg";

import { injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

const inferDbHost = (): string => {
  const apiUrl = process.env.E2E_API_URL ?? "";
  return apiUrl.includes("://backend:") ? "postgres" : "localhost";
};

const getDbConfig = () => {
  const connectionString = process.env.E2E_DB_URL;
  if (connectionString) return { connectionString };
  return {
    host: process.env.E2E_DB_HOST ?? inferDbHost(),
    port: Number(process.env.E2E_DB_PORT ?? 5432),
    user: process.env.E2E_DB_USER ?? "vocabapp",
    password: process.env.E2E_DB_PASSWORD ?? "devpassword",
    database: process.env.E2E_DB_NAME ?? "vocabapp_dev",
  };
};

test("@smoke admin can browse mixed-family final DB entries", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-db-inspector-smoke");
  const suffix = `${Date.now()}${test.info().workerIndex}`;
  const wordText = `inspect${suffix}`;
  const phraseText = `inspect phrase ${suffix}`;
  const referenceText = `InspectRef${suffix}`;

  const client = new Client(getDbConfig());
  await client.connect();
  try {
    await client.query(
      `
      INSERT INTO lexicon.words (id, word, language, cefr_level, frequency_rank, source_reference)
      VALUES (gen_random_uuid(), $1, 'en', 'B1', 100, 'e2e-inspector')
      ON CONFLICT DO NOTHING
      RETURNING id::text AS id
      `,
      [wordText],
    );
    const wordResult = await client.query<{ id: string }>(
      `
      SELECT id::text AS id FROM lexicon.words WHERE word = $1 AND language = 'en'
      `,
      [wordText],
    );
    await client.query(
      `
      INSERT INTO lexicon.phrase_entries (id, phrase_text, normalized_form, phrase_kind, language, cefr_level, source_reference)
      VALUES (gen_random_uuid(), $1, $2, 'idiom', 'en', 'B2', 'e2e-inspector')
      ON CONFLICT DO NOTHING
      `,
      [phraseText, phraseText],
    );
    const referenceResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.reference_entries (
        id, reference_type, display_form, normalized_form, translation_mode, brief_description, pronunciation, language, source_reference
      )
      VALUES (gen_random_uuid(), 'name', $1, $2, 'borrowed', 'reference smoke', 'ref', 'en', 'e2e-inspector')
      ON CONFLICT (normalized_form, language) DO UPDATE SET display_form = EXCLUDED.display_form
      RETURNING id::text AS id
      `,
      [referenceText, referenceText.toLowerCase()],
    );
    await client.query(
      `
      INSERT INTO lexicon.reference_localizations (id, reference_entry_id, locale, display_form, brief_description, translation_mode)
      VALUES (gen_random_uuid(), $1::uuid, 'ja', $2, '参照スモーク', 'borrowed')
      ON CONFLICT (reference_entry_id, locale) DO UPDATE SET display_form = EXCLUDED.display_form
      `,
      [referenceResult.rows[0].id, `ロンドン${suffix}`],
    );
    await client.query(
      `
      INSERT INTO lexicon.lexicon_voice_storage_policies (
        id,
        policy_key,
        source_reference,
        content_scope,
        provider,
        family,
        locale,
        primary_storage_kind,
        primary_storage_base
      )
      VALUES (
        gen_random_uuid(),
        'word_default',
        'global',
        'word',
        'default',
        'default',
        'all',
        'remote',
        'https://cdn.example.com/lexicon'
      )
      ON CONFLICT (policy_key) DO UPDATE
      SET
        primary_storage_kind = EXCLUDED.primary_storage_kind,
        primary_storage_base = EXCLUDED.primary_storage_base
      `,
    );
    await client.query(
      `
      INSERT INTO lexicon.lexicon_voice_assets (
        id, word_id, storage_policy_id, content_scope, locale, voice_role, provider, family, voice_id, profile_key,
        audio_format, mime_type, lead_ms, tail_ms, relative_path,
        source_text, source_text_hash, status
      )
      VALUES (
        gen_random_uuid(),
        $1::uuid,
        (SELECT id FROM lexicon.lexicon_voice_storage_policies WHERE policy_key = 'word_default'),
        'word',
        'en-US',
        'female',
        'google',
        'neural2',
        'en-US-Neural2-C',
        'word',
        'mp3',
        'audio/mpeg',
        140,
        220,
        $2,
        $3,
        md5($3),
        'generated'
      )
      ON CONFLICT DO NOTHING
      `,
      [wordResult.rows[0].id, `${wordText}/word/en_us/female-word.mp3`, wordText],
    );
  } finally {
    await client.end();
  }

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/lexicon/db-inspector`);
  await expect(page.getByTestId("lexicon-db-inspector-page")).toBeVisible();
  await expect(page.getByTestId("lexicon-db-inspector-results")).toContainText(wordText);
  await page.getByRole("button", { name: new RegExp(`^${wordText}`) }).click();
  await expect(page.getByTestId("lexicon-db-inspector-detail")).toContainText("Voice assets");
  await expect(page.getByTestId("lexicon-db-inspector-detail")).toContainText("Word · en-US · female");

  await page.getByTestId("lexicon-db-inspector-family-filter").selectOption("phrase");
  await expect(page.getByTestId("lexicon-db-inspector-results")).toContainText(phraseText);

  await page.getByTestId("lexicon-db-inspector-family-filter").selectOption("reference");
  await page.getByTestId("lexicon-db-inspector-search-input").fill(referenceText);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("lexicon-db-inspector-results")).toContainText(referenceText);
  await page.getByRole("button", { name: new RegExp(`^${referenceText}`) }).click();
  await expect(page.getByTestId("lexicon-db-inspector-detail")).toContainText("reference");
  await expect(page.getByTestId("lexicon-db-inspector-detail")).toContainText("borrowed");
});
