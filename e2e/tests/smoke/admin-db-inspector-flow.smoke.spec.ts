import { expect, test } from "@playwright/test";
import { Client } from "pg";

import { injectAdminToken, registerAdminViaApi } from "../helpers/auth";

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
  } finally {
    await client.end();
  }

  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/lexicon/db-inspector`);
  await expect(page.getByTestId("lexicon-db-inspector-page")).toBeVisible();
  await expect(page.getByTestId("lexicon-db-inspector-results")).toContainText(wordText);

  await page.getByTestId("lexicon-db-inspector-family-filter").selectOption("phrase");
  await expect(page.getByTestId("lexicon-db-inspector-results")).toContainText(phraseText);

  await page.getByTestId("lexicon-db-inspector-family-filter").selectOption("reference");
  await page.getByTestId("lexicon-db-inspector-search-input").fill(referenceText);
  await expect(page.getByTestId("lexicon-db-inspector-results")).toContainText(referenceText);
  await page.getByRole("button", { name: new RegExp(`^${referenceText}`) }).click();
  await expect(page.getByTestId("lexicon-db-inspector-detail")).toContainText("reference");
  await expect(page.getByTestId("lexicon-db-inspector-detail")).toContainText("borrowed");
});
