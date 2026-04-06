import { randomUUID } from "node:crypto";
import { Client } from "pg";

const KNOWLEDGE_WORD_ID = "33333333-3333-3333-3333-333333333333";
const KNOWLEDGE_MEANING_ID = "44444444-4444-4444-4444-444444444444";
const KNOWLEDGE_TRANSLATION_ID = "55555555-5555-5555-5555-555555555555";
const KNOWLEDGE_EXAMPLE_ID = "66666666-6666-6666-6666-666666666666";
const KNOWLEDGE_PHRASE_ID = "77777777-7777-7777-7777-777777777777";
const KNOWLEDGE_PHRASE_SENSE_ID = "77777777-7777-7777-7777-777777777778";
const KNOWLEDGE_PHRASE_SENSE_LOCALIZATION_ID = "77777777-7777-7777-7777-777777777779";
const KNOWLEDGE_PHRASE_EXAMPLE_ID = "77777777-7777-7777-7777-777777777780";
const KNOWLEDGE_PHRASE_EXAMPLE_LOCALIZATION_ID = "77777777-7777-7777-7777-777777777781";
const KNOWLEDGE_PHRASE_EXAMPLE_TWO_ID = "77777777-7777-7777-7777-777777777782";
const KNOWLEDGE_PHRASE_EXAMPLE_TWO_LOCALIZATION_ID = "77777777-7777-7777-7777-777777777783";
const WORD_POLICY_ID = "12121212-1212-1212-1212-121212121212";
const DEFINITION_POLICY_ID = "13131313-1313-1313-1313-131313131313";
const EXAMPLE_POLICY_ID = "14141414-1414-1414-1414-141414141414";
const KNOWLEDGE_WORD_VOICE_US_ID = "15151515-1515-1515-1515-151515151515";
const KNOWLEDGE_WORD_VOICE_UK_ID = "16161616-1616-1616-1616-161616161616";
const KNOWLEDGE_MEANING_VOICE_US_ID = "17171717-1717-1717-1717-171717171717";
const KNOWLEDGE_EXAMPLE_VOICE_US_ID = "18181818-1818-1818-1818-181818181818";
const KNOWLEDGE_PHRASE_VOICE_US_ID = "19191919-1919-1919-1919-191919191919";
const KNOWLEDGE_PHRASE_VOICE_UK_ID = "20202020-2020-2020-2020-202020202020";
const KNOWLEDGE_PHRASE_SENSE_VOICE_US_ID = "21212121-2121-2121-2121-212121212121";
const KNOWLEDGE_PHRASE_EXAMPLE_VOICE_US_ID = "22222222-2222-2222-2222-222222222222";
const LEARN_WORD_ID = "88888888-8888-8888-8888-888888888888";
const LEARN_MEANING_ID = "99999999-9999-9999-9999-999999999999";
const LEARN_TRANSLATION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const LEARN_EXAMPLE_ID = "abababab-abab-abab-abab-abababababab";
const LEARN_WORD_VOICE_US_ID = "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1";
const LEARN_WORD_VOICE_UK_ID = "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2";
const LEARN_MEANING_VOICE_US_ID = "b3b3b3b3-b3b3-b3b3-b3b3-b3b3b3b3b3b3";
const LEARN_EXAMPLE_VOICE_US_ID = "b4b4b4b4-b4b4-b4b4-b4b4-b4b4b4b4b4b4";

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
        frequency_rank,
        created_at
      )
      VALUES (
        $1::uuid,
        $2,
        'en',
        $3::json,
        $4,
        20,
        now()
      )
      ON CONFLICT (word, language)
      DO UPDATE SET
        phonetics = EXCLUDED.phonetics,
        phonetic = EXCLUDED.phonetic,
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
      ],
    );
    const wordId = wordResult.rows[0]?.id;
    if (!wordId) {
      throw new Error("Failed to upsert learner knowledge-map word fixture");
    }
    await client.query(`DELETE FROM lexicon.word_part_of_speech WHERE word_id = $1::uuid`, [wordId]);
    await client.query(
      `
      INSERT INTO lexicon.word_part_of_speech (id, word_id, value, order_index, created_at)
      VALUES ($1::uuid, $2::uuid, 'noun', 0, now())
      `,
      [randomUUID(), wordId],
    );

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
        frequency_rank,
        created_at
      )
      VALUES (
        $1::uuid,
        $2,
        'en',
        $3::json,
        $4,
        2616,
        now()
      )
      ON CONFLICT (word, language)
      DO UPDATE SET
        phonetics = EXCLUDED.phonetics,
        phonetic = EXCLUDED.phonetic,
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
      ],
    );
    const learnWordId = learnWordResult.rows[0]?.id;
    if (!learnWordId) {
      throw new Error("Failed to upsert learner next-learn word fixture");
    }
    await client.query(`DELETE FROM lexicon.word_part_of_speech WHERE word_id = $1::uuid`, [learnWordId]);
    await client.query(
      `
      INSERT INTO lexicon.word_part_of_speech (id, word_id, value, order_index, created_at)
      VALUES ($1::uuid, $2::uuid, 'noun', 0, now())
      `,
      [randomUUID(), learnWordId],
    );

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
        'B1',
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
        LEARN_EXAMPLE_ID,
        LEARN_MEANING_ID,
        "The drummer carried the rhythm through the song.",
      ],
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
                {
                  id: "phrase-example-2",
                  sentence: "Investors bank on steady demand in the winter season.",
                  difficulty: "B2",
                },
              ],
              translations: {
                es: {
                  definition: "depender de",
                  examples: [
                    "Puedes depender de mi cuando el plazo es corto.",
                    "Los inversores dependen de una demanda estable en la temporada de invierno.",
                  ],
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
      DELETE FROM lexicon.phrase_senses
      WHERE phrase_entry_id = $1::uuid
      `,
      [phraseId],
    );

    const phraseSenseResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.phrase_senses (
        id,
        phrase_entry_id,
        definition,
        usage_note,
        part_of_speech,
        register,
        primary_domain,
        secondary_domains,
        grammar_patterns,
        synonyms,
        antonyms,
        collocations,
        order_index,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        'To depend on someone or something.',
        'common',
        'phrasal verb',
        'neutral',
        'general',
        '[]'::jsonb,
        '[]'::jsonb,
        '[]'::jsonb,
        '[]'::jsonb,
        '[]'::jsonb,
        0,
        now()
      )
      ON CONFLICT (phrase_entry_id, order_index)
      DO UPDATE SET
        definition = EXCLUDED.definition,
        usage_note = EXCLUDED.usage_note,
        part_of_speech = EXCLUDED.part_of_speech,
        register = EXCLUDED.register,
        primary_domain = EXCLUDED.primary_domain,
        secondary_domains = EXCLUDED.secondary_domains,
        grammar_patterns = EXCLUDED.grammar_patterns,
        synonyms = EXCLUDED.synonyms,
        antonyms = EXCLUDED.antonyms,
        collocations = EXCLUDED.collocations,
        order_index = EXCLUDED.order_index
      RETURNING id::text AS id
      `,
      [KNOWLEDGE_PHRASE_SENSE_ID, phraseId],
    );
    const phraseSenseId = phraseSenseResult.rows[0]?.id;
    if (!phraseSenseId) {
      throw new Error("Failed to upsert learner knowledge-map phrase sense fixture");
    }

    await client.query(
      `
      INSERT INTO lexicon.phrase_sense_localizations (
        id,
        phrase_sense_id,
        locale,
        localized_definition,
        localized_usage_note,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        'es',
        'depender de',
        'common',
        now()
      )
      ON CONFLICT (phrase_sense_id, locale)
      DO UPDATE SET
        localized_definition = EXCLUDED.localized_definition,
        localized_usage_note = EXCLUDED.localized_usage_note
      `,
      [KNOWLEDGE_PHRASE_SENSE_LOCALIZATION_ID, phraseSenseId],
    );

    const phraseExampleResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.phrase_sense_examples (
        id,
        phrase_sense_id,
        sentence,
        difficulty,
        order_index,
        source,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        'You can bank on me when the deadline gets tight.',
        'B1',
        0,
        'e2e-fixture',
        now()
      )
      ON CONFLICT (phrase_sense_id, sentence)
      DO UPDATE SET
        difficulty = EXCLUDED.difficulty,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      RETURNING id::text AS id
      `,
      [KNOWLEDGE_PHRASE_EXAMPLE_ID, phraseSenseId],
    );
    const phraseExampleId = phraseExampleResult.rows[0]?.id;
    if (!phraseExampleId) {
      throw new Error("Failed to upsert learner knowledge-map phrase example fixture");
    }

    await client.query(
      `
      INSERT INTO lexicon.phrase_sense_example_localizations (
        id,
        phrase_sense_example_id,
        locale,
        translation,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        'es',
        'Puedes depender de mi cuando el plazo es corto.',
        now()
      )
      ON CONFLICT (phrase_sense_example_id, locale)
      DO UPDATE SET
        translation = EXCLUDED.translation
      `,
      [KNOWLEDGE_PHRASE_EXAMPLE_LOCALIZATION_ID, phraseExampleId],
    );

    const secondPhraseExampleResult = await client.query<{ id: string }>(
      `
      INSERT INTO lexicon.phrase_sense_examples (
        id,
        phrase_sense_id,
        sentence,
        difficulty,
        order_index,
        source,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        'Investors bank on steady demand in the winter season.',
        'B2',
        1,
        'e2e-fixture',
        now()
      )
      ON CONFLICT (phrase_sense_id, sentence)
      DO UPDATE SET
        difficulty = EXCLUDED.difficulty,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      RETURNING id::text AS id
      `,
      [KNOWLEDGE_PHRASE_EXAMPLE_TWO_ID, phraseSenseId],
    );
    const secondPhraseExampleId = secondPhraseExampleResult.rows[0]?.id;
    if (!secondPhraseExampleId) {
      throw new Error("Failed to upsert learner knowledge-map second phrase example fixture");
    }

    await client.query(
      `
      INSERT INTO lexicon.phrase_sense_example_localizations (
        id,
        phrase_sense_example_id,
        locale,
        translation,
        created_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        'es',
        'Los inversores dependen de una demanda estable en la temporada de invierno.',
        now()
      )
      ON CONFLICT (phrase_sense_example_id, locale)
      DO UPDATE SET
        translation = EXCLUDED.translation
      `,
      [KNOWLEDGE_PHRASE_EXAMPLE_TWO_LOCALIZATION_ID, secondPhraseExampleId],
    );

    const wordPolicy = await client.query<{ id: string }>(
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
        primary_storage_base,
        fallback_storage_kind,
        fallback_storage_base,
        created_at
      )
      VALUES (
        $1::uuid,
        'word_default',
        'global',
        'word',
        'default',
        'default',
        'all',
        'local',
        '/tmp/voice',
        NULL,
        NULL,
        now()
      )
      ON CONFLICT (policy_key)
      DO UPDATE SET
        primary_storage_kind = EXCLUDED.primary_storage_kind,
        primary_storage_base = EXCLUDED.primary_storage_base,
        fallback_storage_kind = EXCLUDED.fallback_storage_kind,
        fallback_storage_base = EXCLUDED.fallback_storage_base
      RETURNING id::text AS id
      `,
      [WORD_POLICY_ID],
    );
    const definitionPolicy = await client.query<{ id: string }>(
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
        primary_storage_base,
        fallback_storage_kind,
        fallback_storage_base,
        created_at
      )
      VALUES (
        $1::uuid,
        'definition_default',
        'global',
        'definition',
        'default',
        'default',
        'all',
        'local',
        '/tmp/voice',
        NULL,
        NULL,
        now()
      )
      ON CONFLICT (policy_key)
      DO UPDATE SET
        primary_storage_kind = EXCLUDED.primary_storage_kind,
        primary_storage_base = EXCLUDED.primary_storage_base,
        fallback_storage_kind = EXCLUDED.fallback_storage_kind,
        fallback_storage_base = EXCLUDED.fallback_storage_base
      RETURNING id::text AS id
      `,
      [DEFINITION_POLICY_ID],
    );
    const examplePolicy = await client.query<{ id: string }>(
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
        primary_storage_base,
        fallback_storage_kind,
        fallback_storage_base,
        created_at
      )
      VALUES (
        $1::uuid,
        'example_default',
        'global',
        'example',
        'default',
        'default',
        'all',
        'local',
        '/tmp/voice',
        NULL,
        NULL,
        now()
      )
      ON CONFLICT (policy_key)
      DO UPDATE SET
        primary_storage_kind = EXCLUDED.primary_storage_kind,
        primary_storage_base = EXCLUDED.primary_storage_base,
        fallback_storage_kind = EXCLUDED.fallback_storage_kind,
        fallback_storage_base = EXCLUDED.fallback_storage_base
      RETURNING id::text AS id
      `,
      [EXAMPLE_POLICY_ID],
    );

    const wordPolicyId = wordPolicy.rows[0]?.id;
    const definitionPolicyId = definitionPolicy.rows[0]?.id;
    const examplePolicyId = examplePolicy.rows[0]?.id;
    if (!wordPolicyId || !definitionPolicyId || !examplePolicyId) {
      throw new Error("Failed to upsert learner voice storage policy fixtures");
    }

    await client.query(
      `
      INSERT INTO lexicon.lexicon_voice_assets (
        id,
        word_id,
        meaning_id,
        meaning_example_id,
        phrase_entry_id,
        phrase_sense_id,
        phrase_sense_example_id,
        storage_policy_id,
        content_scope,
        locale,
        voice_role,
        provider,
        family,
        voice_id,
        profile_key,
        audio_format,
        mime_type,
        relative_path,
        source_text,
        source_text_hash,
        status,
        created_at
      )
      VALUES
        ($1::uuid, $2::uuid, NULL, NULL, NULL, NULL, NULL, $9::uuid, 'word', 'en_us', 'female', 'default', 'default', 'fixture-word-us', 'default', 'mp3', 'audio/mpeg', 'learner/resilience/word/en_us.mp3', 'resilience', md5('resilience-word-us'), 'generated', now()),
        ($3::uuid, $2::uuid, NULL, NULL, NULL, NULL, NULL, $9::uuid, 'word', 'en_gb', 'female', 'default', 'default', 'fixture-word-uk', 'default', 'mp3', 'audio/mpeg', 'learner/resilience/word/en_gb.mp3', 'resilience', md5('resilience-word-uk'), 'generated', now()),
        ($4::uuid, NULL, $5::uuid, NULL, NULL, NULL, NULL, $10::uuid, 'definition', 'en_us', 'female', 'default', 'default', 'fixture-definition-us', 'default', 'mp3', 'audio/mpeg', 'learner/resilience/definition/en_us.mp3', 'The ability to recover quickly from setbacks.', md5('resilience-definition-us'), 'generated', now()),
        ($6::uuid, NULL, NULL, $7::uuid, NULL, NULL, NULL, $11::uuid, 'example', 'en_us', 'female', 'default', 'default', 'fixture-example-us', 'default', 'mp3', 'audio/mpeg', 'learner/resilience/example/en_us.mp3', 'Resilience helps teams adapt to sudden change.', md5('resilience-example-us'), 'generated', now()),
        ($8::uuid, NULL, NULL, NULL, $12::uuid, NULL, NULL, $9::uuid, 'word', 'en_us', 'female', 'default', 'default', 'fixture-phrase-word-us', 'default', 'mp3', 'audio/mpeg', 'learner/bank-on/word/en_us.mp3', 'bank on', md5('bank-on-word-us'), 'generated', now()),
        ($13::uuid, NULL, NULL, NULL, $12::uuid, NULL, NULL, $9::uuid, 'word', 'en_gb', 'female', 'default', 'default', 'fixture-phrase-word-uk', 'default', 'mp3', 'audio/mpeg', 'learner/bank-on/word/en_gb.mp3', 'bank on', md5('bank-on-word-uk'), 'generated', now()),
        ($14::uuid, NULL, NULL, NULL, NULL, $15::uuid, NULL, $10::uuid, 'definition', 'en_us', 'female', 'default', 'default', 'fixture-phrase-definition-us', 'default', 'mp3', 'audio/mpeg', 'learner/bank-on/definition/en_us.mp3', 'To depend on someone or something.', md5('bank-on-definition-us'), 'generated', now()),
        ($16::uuid, NULL, NULL, NULL, NULL, NULL, $17::uuid, $11::uuid, 'example', 'en_us', 'female', 'default', 'default', 'fixture-phrase-example-us', 'default', 'mp3', 'audio/mpeg', 'learner/bank-on/example/en_us.mp3', 'You can bank on me when the deadline gets tight.', md5('bank-on-example-us'), 'generated', now())
      ON CONFLICT (storage_policy_id, relative_path)
      DO UPDATE SET
        word_id = EXCLUDED.word_id,
        meaning_id = EXCLUDED.meaning_id,
        meaning_example_id = EXCLUDED.meaning_example_id,
        phrase_entry_id = EXCLUDED.phrase_entry_id,
        phrase_sense_id = EXCLUDED.phrase_sense_id,
        phrase_sense_example_id = EXCLUDED.phrase_sense_example_id,
        locale = EXCLUDED.locale,
        voice_role = EXCLUDED.voice_role,
        provider = EXCLUDED.provider,
        family = EXCLUDED.family,
        voice_id = EXCLUDED.voice_id,
        profile_key = EXCLUDED.profile_key,
        audio_format = EXCLUDED.audio_format,
        mime_type = EXCLUDED.mime_type,
        source_text = EXCLUDED.source_text,
        source_text_hash = EXCLUDED.source_text_hash,
        status = EXCLUDED.status
      `,
      [
        KNOWLEDGE_WORD_VOICE_US_ID,
        wordId,
        KNOWLEDGE_WORD_VOICE_UK_ID,
        KNOWLEDGE_MEANING_VOICE_US_ID,
        KNOWLEDGE_MEANING_ID,
        KNOWLEDGE_EXAMPLE_VOICE_US_ID,
        KNOWLEDGE_EXAMPLE_ID,
        KNOWLEDGE_PHRASE_VOICE_US_ID,
        wordPolicyId,
        definitionPolicyId,
        examplePolicyId,
        phraseId,
        KNOWLEDGE_PHRASE_VOICE_UK_ID,
        KNOWLEDGE_PHRASE_SENSE_VOICE_US_ID,
        phraseSenseId,
        KNOWLEDGE_PHRASE_EXAMPLE_VOICE_US_ID,
        phraseExampleId,
      ],
    );

    await client.query(
      `
      INSERT INTO lexicon.lexicon_voice_assets (
        id,
        word_id,
        meaning_id,
        meaning_example_id,
        phrase_entry_id,
        phrase_sense_id,
        phrase_sense_example_id,
        storage_policy_id,
        content_scope,
        locale,
        voice_role,
        provider,
        family,
        voice_id,
        profile_key,
        audio_format,
        mime_type,
        relative_path,
        source_text,
        source_text_hash,
        status,
        created_at
      )
      VALUES
        ($1::uuid, $2::uuid, NULL, NULL, NULL, NULL, NULL, $6::uuid, 'word', 'en_us', 'female', 'default', 'default', 'fixture-learn-word-us', 'default', 'mp3', 'audio/mpeg', 'learner/drum/word/en_us.mp3', 'drum', md5('drum-word-us'), 'generated', now()),
        ($3::uuid, $2::uuid, NULL, NULL, NULL, NULL, NULL, $6::uuid, 'word', 'en_gb', 'female', 'default', 'default', 'fixture-learn-word-uk', 'default', 'mp3', 'audio/mpeg', 'learner/drum/word/en_gb.mp3', 'drum', md5('drum-word-uk'), 'generated', now()),
        ($4::uuid, NULL, $5::uuid, NULL, NULL, NULL, NULL, $7::uuid, 'definition', 'en_us', 'female', 'default', 'default', 'fixture-learn-definition-us', 'default', 'mp3', 'audio/mpeg', 'learner/drum/definition/en_us.mp3', 'A percussion instrument played by striking it.', md5('drum-definition-us'), 'generated', now()),
        ($8::uuid, NULL, NULL, $9::uuid, NULL, NULL, NULL, $10::uuid, 'example', 'en_us', 'female', 'default', 'default', 'fixture-learn-example-us', 'default', 'mp3', 'audio/mpeg', 'learner/drum/example/en_us.mp3', 'The drummer carried the rhythm through the song.', md5('drum-example-us'), 'generated', now())
      ON CONFLICT (storage_policy_id, relative_path)
      DO UPDATE SET
        word_id = EXCLUDED.word_id,
        meaning_id = EXCLUDED.meaning_id,
        meaning_example_id = EXCLUDED.meaning_example_id,
        phrase_entry_id = EXCLUDED.phrase_entry_id,
        phrase_sense_id = EXCLUDED.phrase_sense_id,
        phrase_sense_example_id = EXCLUDED.phrase_sense_example_id,
        locale = EXCLUDED.locale,
        voice_role = EXCLUDED.voice_role,
        provider = EXCLUDED.provider,
        family = EXCLUDED.family,
        voice_id = EXCLUDED.voice_id,
        profile_key = EXCLUDED.profile_key,
        audio_format = EXCLUDED.audio_format,
        mime_type = EXCLUDED.mime_type,
        source_text = EXCLUDED.source_text,
        source_text_hash = EXCLUDED.source_text_hash,
        status = EXCLUDED.status
      `,
      [
        LEARN_WORD_VOICE_US_ID,
        learnWordId,
        LEARN_WORD_VOICE_UK_ID,
        LEARN_MEANING_VOICE_US_ID,
        LEARN_MEANING_ID,
        wordPolicyId,
        definitionPolicyId,
        LEARN_EXAMPLE_VOICE_US_ID,
        LEARN_EXAMPLE_ID,
        examplePolicyId,
      ],
    );

    await client.query(
      `
      DELETE FROM lexicon.learner_catalog_entries
      WHERE (entry_type = 'word' AND entry_id IN ($1::uuid, $2::uuid))
         OR (entry_type = 'phrase' AND entry_id = $3::uuid)
      `,
      [wordId, learnWordId, phraseId],
    );

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
      VALUES
        (
          gen_random_uuid(),
          'word',
          $1::uuid,
          $2::text,
          lower($2::text),
          20,
          1,
          NULL,
          'noun',
          NULL,
          true,
          now()
        ),
        (
          gen_random_uuid(),
          'word',
          $3::uuid,
          $4::text,
          lower($4::text),
          2616,
          2601,
          NULL,
          'noun',
          NULL,
          true,
          now()
        )
      `,
      [wordId, KNOWLEDGE_WORD, learnWordId, LEARN_WORD],
    );

    await client.query(
      `
      WITH next_rank AS (
        SELECT COALESCE(MAX(browse_rank), 0) + 1 AS browse_rank
        FROM lexicon.learner_catalog_entries
      )
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
      SELECT
        gen_random_uuid(),
        'phrase',
        $1::uuid,
        $2::text,
        lower($3::text),
        next_rank.browse_rank,
        ((next_rank.browse_rank - 1) / 100) * 100 + 1,
        'B1',
        NULL,
        'phrasal_verb',
        false,
        now()
      FROM next_rank
      `,
      [phraseId, KNOWLEDGE_PHRASE, KNOWLEDGE_PHRASE],
    );

    await client.query(
      `
      INSERT INTO user_preferences (
        id,
        user_id,
        accent_preference,
        translation_locale,
        knowledge_view_preference,
        review_depth_preset,
        timezone,
        enable_confidence_check,
        enable_word_spelling,
        enable_audio_spelling,
        show_pictures_in_questions
      )
      VALUES ($1::uuid, $2::uuid, 'uk', 'es', 'cards', 'balanced', 'UTC', true, true, false, false)
      ON CONFLICT (user_id)
      DO UPDATE SET
        accent_preference = EXCLUDED.accent_preference,
        translation_locale = EXCLUDED.translation_locale,
        knowledge_view_preference = EXCLUDED.knowledge_view_preference,
        review_depth_preset = EXCLUDED.review_depth_preset,
        timezone = EXCLUDED.timezone,
        enable_confidence_check = EXCLUDED.enable_confidence_check,
        enable_word_spelling = EXCLUDED.enable_word_spelling,
        enable_audio_spelling = EXCLUDED.enable_audio_spelling,
        show_pictures_in_questions = EXCLUDED.show_pictures_in_questions,
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
