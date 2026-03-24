import { randomUUID } from "node:crypto";
import { Client } from "pg";

const KNOWLEDGE_WORD_ID = "33333333-3333-3333-3333-333333333333";
const KNOWLEDGE_MEANING_ID = "44444444-4444-4444-4444-444444444444";
const KNOWLEDGE_TRANSLATION_ID = "55555555-5555-5555-5555-555555555555";
const KNOWLEDGE_EXAMPLE_ID = "66666666-6666-6666-6666-666666666666";
const KNOWLEDGE_PHRASE_ID = "77777777-7777-7777-7777-777777777777";
const LEARN_WORD_ID = "88888888-8888-8888-8888-888888888888";
const LEARN_MEANING_ID = "99999999-9999-9999-9999-999999999999";
const LEARN_TRANSLATION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

export const KNOWLEDGE_WORD = "resilience";
export const KNOWLEDGE_PHRASE = "bank on";
export const LEARN_WORD = "drum";

type FixtureIds = {
  wordId: string;
  phraseId: string;
  learnWordId: string;
};

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

export const seedKnowledgeMapFixture = async (userId: string): Promise<FixtureIds> => {
  const client = new Client(getDbConfig());
  await client.connect();

  try {
    await client.query("BEGIN");

    const wordResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.words (
        id,
        word,
        language,
        phonetics,
        phonetic,
        learner_part_of_speech,
        frequency_rank,
        created_at
      )
      VALUES (
        $1::uuid,
        $2,
        'en',
        $3::json,
        $4,
        $5::json,
        20,
        now()
      )
      ON CONFLICT (word, language)
      DO UPDATE SET
        phonetics = EXCLUDED.phonetics,
        phonetic = EXCLUDED.phonetic,
        learner_part_of_speech = EXCLUDED.learner_part_of_speech,
        frequency_rank = EXCLUDED.frequency_rank
      RETURNING id::text AS id
      `,
      [
        KNOWLEDGE_WORD_ID,
        KNOWLEDGE_WORD,
        JSON.stringify({
          us: { ipa: "/rɪˈzɪliəns/", confidence: 0.99 },
          uk: { ipa: "/rɪˈzɪliəns/", confidence: 0.99 },
        }),
        "/rɪˈzɪliəns/",
        JSON.stringify(["noun"]),
      ],
    );
    const wordId = wordResult.rows[0]?.id;
    if (!wordId) {
      throw new Error("Failed to upsert learner knowledge-map word fixture");
    }

    await client.query(
      `
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
      VALUES (
        $1::uuid,
        $2::uuid,
        $3,
        'noun',
        $4,
        0,
        'e2e-fixture',
        now()
      )
      ON CONFLICT (id)
      DO UPDATE SET
        word_id = EXCLUDED.word_id,
        definition = EXCLUDED.definition,
        part_of_speech = EXCLUDED.part_of_speech,
        example_sentence = EXCLUDED.example_sentence,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      `,
      [
        KNOWLEDGE_MEANING_ID,
        wordId,
        "The ability to recover quickly from setbacks.",
        "Resilience helps teams adapt to sudden change.",
      ],
    );

    await client.query(
      `
      INSERT INTO lexicon.translations (id, meaning_id, language, translation)
      VALUES ($1::uuid, $2::uuid, 'es', 'resiliencia')
      ON CONFLICT (meaning_id, language)
      DO UPDATE SET translation = EXCLUDED.translation
      `,
      [KNOWLEDGE_TRANSLATION_ID, KNOWLEDGE_MEANING_ID],
    );

    await client.query(
      `
      INSERT INTO lexicon.meaning_examples (
        id,
        meaning_id,
        sentence,
        difficulty,
        order_index,
        source,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        $3,
        'B2',
        0,
        'e2e-fixture',
        now()
      )
      ON CONFLICT (meaning_id, sentence)
      DO UPDATE SET
        difficulty = EXCLUDED.difficulty,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      `,
      [
        KNOWLEDGE_EXAMPLE_ID,
        KNOWLEDGE_MEANING_ID,
        "Resilience helps teams adapt to sudden change.",
      ],
    );

    const learnWordResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.words (
        id,
        word,
        language,
        phonetics,
        phonetic,
        learner_part_of_speech,
        frequency_rank,
        created_at
      )
      VALUES (
        $1::uuid,
        $2,
        'en',
        $3::json,
        $4,
        $5::json,
        2616,
        now()
      )
      ON CONFLICT (word, language)
      DO UPDATE SET
        phonetics = EXCLUDED.phonetics,
        phonetic = EXCLUDED.phonetic,
        learner_part_of_speech = EXCLUDED.learner_part_of_speech,
        frequency_rank = EXCLUDED.frequency_rank
      RETURNING id::text AS id
      `,
      [
        LEARN_WORD_ID,
        LEARN_WORD,
        JSON.stringify({
          us: { ipa: "/drʌm/", confidence: 0.99 },
          uk: { ipa: "/drʌm/", confidence: 0.99 },
        }),
        "/drʌm/",
        JSON.stringify(["noun"]),
      ],
    );
    const learnWordId = learnWordResult.rows[0]?.id;
    if (!learnWordId) {
      throw new Error("Failed to upsert learner next-learn word fixture");
    }

    await client.query(
      `
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
      VALUES (
        $1::uuid,
        $2::uuid,
        'A percussion instrument played by striking it.',
        'noun',
        'The drummer carried the rhythm through the song.',
        0,
        'e2e-fixture',
        now()
      )
      ON CONFLICT (id)
      DO UPDATE SET
        word_id = EXCLUDED.word_id,
        definition = EXCLUDED.definition,
        part_of_speech = EXCLUDED.part_of_speech,
        example_sentence = EXCLUDED.example_sentence,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      `,
      [LEARN_MEANING_ID, learnWordId],
    );

    await client.query(
      `
      INSERT INTO lexicon.translations (id, meaning_id, language, translation)
      VALUES ($1::uuid, $2::uuid, 'es', 'tambor')
      ON CONFLICT (meaning_id, language)
      DO UPDATE SET translation = EXCLUDED.translation
      `,
      [LEARN_TRANSLATION_ID, LEARN_MEANING_ID],
    );

    const phraseResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.phrase_entries (
        id,
        phrase_text,
        normalized_form,
        phrase_kind,
        language,
        cefr_level,
        compiled_payload,
        created_at
      )
      VALUES (
        $1::uuid,
        $2,
        $3,
        'phrasal_verb',
        'en',
        'B1',
        $4::jsonb,
        now()
      )
      ON CONFLICT (normalized_form, language)
      DO UPDATE SET
        phrase_text = EXCLUDED.phrase_text,
        phrase_kind = EXCLUDED.phrase_kind,
        cefr_level = EXCLUDED.cefr_level,
        compiled_payload = EXCLUDED.compiled_payload
      RETURNING id::text AS id
      `,
      [
        KNOWLEDGE_PHRASE_ID,
        KNOWLEDGE_PHRASE,
        KNOWLEDGE_PHRASE,
        JSON.stringify({
          senses: [
            {
              sense_id: "phrase-sense-1",
              definition: "To depend on someone or something.",
              part_of_speech: "phrasal verb",
              examples: [
                {
                  id: "phrase-example-1",
                  sentence: "You can bank on me when the deadline gets tight.",
                  difficulty: "B1",
                },
              ],
              translations: {
                es: {
                  definition: "depender de",
                  examples: ["Puedes depender de mi cuando el plazo es corto."],
                  usage_note: "common",
                },
              },
            },
          ],
        }),
      ],
    );
    const phraseId = phraseResult.rows[0]?.id;
    if (!phraseId) {
      throw new Error("Failed to upsert learner knowledge-map phrase fixture");
    }

    await client.query(
      `
      INSERT INTO user_preferences (id, user_id, accent_preference, translation_locale, knowledge_view_preference)
      VALUES ($1::uuid, $2::uuid, 'uk', 'es', 'cards')
      ON CONFLICT (user_id)
      DO UPDATE SET
        accent_preference = EXCLUDED.accent_preference,
        translation_locale = EXCLUDED.translation_locale,
        knowledge_view_preference = EXCLUDED.knowledge_view_preference,
        updated_at = now()
      `,
      [randomUUID(), userId],
    );

    await client.query(
      `
      INSERT INTO learner_entry_statuses (id, user_id, entry_type, entry_id, status)
      SELECT gen_random_uuid(), $1::uuid, 'word', id, 'known'
      FROM lexicon.words
      WHERE frequency_rank IS NOT NULL
        AND frequency_rank < 2616
      ON CONFLICT (user_id, entry_type, entry_id)
      DO UPDATE SET status = EXCLUDED.status, updated_at = now()
      `,
      [userId],
    );

    await client.query(
      `
      INSERT INTO learner_entry_statuses (id, user_id, entry_type, entry_id, status)
      VALUES ($1::uuid, $2::uuid, 'phrase', $3::uuid, 'learning')
      ON CONFLICT (user_id, entry_type, entry_id)
      DO UPDATE SET status = EXCLUDED.status, updated_at = now()
      `,
      [randomUUID(), userId, phraseId],
    );

    await client.query(
      `
      INSERT INTO learner_entry_statuses (id, user_id, entry_type, entry_id, status)
      VALUES ($1::uuid, $2::uuid, 'word', $3::uuid, 'to_learn')
      ON CONFLICT (user_id, entry_type, entry_id)
      DO UPDATE SET status = EXCLUDED.status, updated_at = now()
      `,
      [randomUUID(), userId, learnWordId],
    );

    await client.query("COMMIT");
    return {
      wordId,
      phraseId,
      learnWordId,
    };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};
