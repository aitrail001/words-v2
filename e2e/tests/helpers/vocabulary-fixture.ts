import { Client } from "pg";

const RESILIENCE_WORD_ID = "11111111-1111-1111-1111-111111111111";
const RESILIENCE_MEANING_ID = "22222222-2222-2222-2222-222222222222";
const RESILIENCE_WORD = "resilience";
const RESILIENCE_DEFINITION = "The capacity to recover quickly from difficulties.";
const RESILIENCE_EXAMPLE = "Resilience helps teams adapt to change.";
const RESILIENCE_FREQUENCY_RANK = 2500;

type FixtureIds = {
  wordId: string;
  meaningId: string;
};

let fixturePromise: Promise<FixtureIds> | null = null;

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

const seedFixture = async (): Promise<FixtureIds> => {
  const client = new Client(getDbConfig());
  await client.connect();

  try {
    await client.query("BEGIN");

    const result = await client.query<{
      word_id: string;
      meaning_id: string;
    }>(
      `
      WITH upsert_word AS (
        INSERT INTO lexicon.words (id, word, language, phonetic, frequency_rank, created_at)
        VALUES ($1::uuid, $2, 'en', NULL, $3, now())
        ON CONFLICT (word, language)
        DO UPDATE SET frequency_rank = EXCLUDED.frequency_rank
        RETURNING id
      ),
      upsert_meaning AS (
        INSERT INTO lexicon.meanings (
          id,
          word_id,
          definition,
          part_of_speech,
          example_sentence,
          order_index,
          source,
          created_at
        )
        SELECT
          $4::uuid,
          id,
          $5,
          'noun',
          $6,
          0,
          'e2e-fixture',
          now()
        FROM upsert_word
        ON CONFLICT (id)
        DO UPDATE SET
          word_id = EXCLUDED.word_id,
          definition = EXCLUDED.definition,
          part_of_speech = EXCLUDED.part_of_speech,
          example_sentence = EXCLUDED.example_sentence,
          order_index = EXCLUDED.order_index,
          source = EXCLUDED.source
        RETURNING id, word_id
      )
      SELECT
        upsert_word.id::text AS word_id,
        upsert_meaning.id::text AS meaning_id
      FROM upsert_word
      JOIN upsert_meaning ON upsert_meaning.word_id = upsert_word.id
      `,
      [
        RESILIENCE_WORD_ID,
        RESILIENCE_WORD,
        RESILIENCE_FREQUENCY_RANK,
        RESILIENCE_MEANING_ID,
        RESILIENCE_DEFINITION,
        RESILIENCE_EXAMPLE,
      ],
    );

    await client.query("COMMIT");

    const row = result.rows[0];
    if (!row) {
      throw new Error("Failed to create resilience vocabulary fixture");
    }

    return {
      wordId: row.word_id,
      meaningId: row.meaning_id,
    };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};

export const ensureResilienceVocabularyFixture = async (): Promise<FixtureIds> => {
  if (!fixturePromise) {
    fixturePromise = seedFixture().catch((error) => {
      fixturePromise = null;
      throw error;
    });
  }
  return fixturePromise;
};
