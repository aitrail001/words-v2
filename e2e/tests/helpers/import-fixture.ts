import crypto from "node:crypto";
import fs from "node:fs/promises";
import { Client } from "pg";

const IMPORT_PHRASE_ID = "33333333-3333-3333-3333-333333333333";
const IMPORT_PHRASE_TEXT = "learning words";

const inferDbHost = (): string => {
  const apiUrl = process.env.E2E_API_URL ?? "";
  return apiUrl.includes("://backend:") ? "postgres" : "localhost";
};

const getDbConfig = () => {
  const connectionString = process.env.E2E_DB_URL;
  if (connectionString) {
    return { connectionString };
  }

  return {
    host: process.env.E2E_DB_HOST ?? inferDbHost(),
    port: Number(process.env.E2E_DB_PORT ?? 5432),
    user: process.env.E2E_DB_USER ?? "vocabapp",
    password: process.env.E2E_DB_PASSWORD ?? "devpassword",
    database: process.env.E2E_DB_NAME ?? "vocabapp_dev",
  };
};

const sha256File = async (filePath: string): Promise<string> => {
  const buffer = await fs.readFile(filePath);
  return crypto.createHash("sha256").update(buffer).digest("hex");
};

export const prepareImportFixture = async (epubPath: string): Promise<void> => {
  const sourceHash = await sha256File(epubPath);
  const client = new Client(getDbConfig());
  await client.connect();

  try {
    await client.query("BEGIN");

    await client.query(
      `
      INSERT INTO lexicon.learner_catalog_entries (
        id,
        entry_type,
        entry_id,
        display_text,
        normalized_form,
        browse_rank,
        bucket_start,
        cefr_level,
        primary_part_of_speech,
        phrase_kind,
        is_ranked,
        created_at
      )
      VALUES (
        gen_random_uuid(),
        'phrase',
        $1::uuid,
        $2::text,
        lower($2::text),
        4001,
        4001,
        'B1',
        NULL,
        'phrase',
        false,
        now()
      )
      ON CONFLICT (entry_type, entry_id)
      DO UPDATE SET
        display_text = EXCLUDED.display_text,
        normalized_form = EXCLUDED.normalized_form,
        browse_rank = EXCLUDED.browse_rank,
        bucket_start = EXCLUDED.bucket_start,
        cefr_level = EXCLUDED.cefr_level,
        primary_part_of_speech = EXCLUDED.primary_part_of_speech,
        phrase_kind = EXCLUDED.phrase_kind,
        is_ranked = EXCLUDED.is_ranked
      `,
      [IMPORT_PHRASE_ID, IMPORT_PHRASE_TEXT],
    );

    await client.query(
      `
      DELETE FROM import_jobs
      WHERE source_hash = $1
      `,
      [sourceHash],
    );

    await client.query(
      `
      DELETE FROM import_source_entries
      WHERE import_source_id IN (
        SELECT id
        FROM import_sources
        WHERE source_type = 'epub'
          AND source_hash_sha256 = $1
      )
      `,
      [sourceHash],
    );

    await client.query(
      `
      DELETE FROM import_sources
      WHERE source_type = 'epub'
        AND source_hash_sha256 = $1
      `,
      [sourceHash],
    );

    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};
