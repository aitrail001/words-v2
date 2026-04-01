import { Client } from "pg";

const REAL_WORD_ID = "f1111111-1111-1111-1111-111111111111";
const REAL_PHRASE_ID = "f2222222-2222-2222-2222-222222222222";
const REAL_VOICE_POLICY_ID = "f3333333-3333-3333-3333-333333333333";
const REAL_WORD_VOICE_US_ID = "f4444444-4444-4444-4444-444444444444";
const REAL_WORD_VOICE_UK_ID = "f5555555-5555-5555-5555-555555555555";
const REAL_PHRASE_VOICE_US_ID = "f6666666-6666-6666-6666-666666666666";
const REAL_PHRASE_VOICE_UK_ID = "f7777777-7777-7777-7777-777777777777";
const REAL_VOICE_STORAGE_BASE = "/app/data/e2e/voice/review-live";

export const REAL_WORD_TEXT = "ability";
export const REAL_PHRASE_TEXT = "a blessing in disguise";

type RealVoiceFixture = {
  wordId: string;
  phraseId: string;
  wordVoiceUsId: string;
  wordVoiceUkId: string;
  phraseVoiceUsId: string;
  phraseVoiceUkId: string;
};

let fixturePromise: Promise<RealVoiceFixture> | null = null;

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

const seedFixture = async (): Promise<RealVoiceFixture> => {
  const client = new Client(getDbConfig());
  await client.connect();

  try {
    await client.query("BEGIN");

    await client.query(
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
        '/əˈbɪl.ə.ti/',
        42,
        now()
      )
      ON CONFLICT (word, language)
      DO UPDATE SET
        phonetics = EXCLUDED.phonetics,
        phonetic = EXCLUDED.phonetic,
        frequency_rank = EXCLUDED.frequency_rank
      `,
      [
        REAL_WORD_ID,
        REAL_WORD_TEXT,
        JSON.stringify({
          us: { ipa: "/əˈbɪləti/", confidence: 0.99 },
          uk: { ipa: "/əˈbɪl.ə.ti/", confidence: 0.99 },
        }),
      ],
    );

    await client.query(`DELETE FROM lexicon.word_part_of_speech WHERE word_id = $1::uuid`, [
      REAL_WORD_ID,
    ]);
    await client.query(
      `
      INSERT INTO lexicon.word_part_of_speech (id, word_id, value, order_index, created_at)
      VALUES (gen_random_uuid(), $1::uuid, 'noun', 0, now())
      `,
      [REAL_WORD_ID],
    );

    await client.query(
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
        $2,
        'idiom',
        'en',
        'B2',
        $3::jsonb,
        now()
      )
      ON CONFLICT (normalized_form, language)
      DO UPDATE SET
        phrase_text = EXCLUDED.phrase_text,
        phrase_kind = EXCLUDED.phrase_kind,
        cefr_level = EXCLUDED.cefr_level,
        compiled_payload = EXCLUDED.compiled_payload
      `,
      [
        REAL_PHRASE_ID,
        REAL_PHRASE_TEXT,
        JSON.stringify({
          senses: [
            {
              sense_id: "real-phrase-sense-1",
              definition: "Something that seems bad at first but later turns out to be good.",
              part_of_speech: "idiom",
              examples: [],
            },
          ],
        }),
      ],
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
        $2,
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
      `,
      [REAL_VOICE_POLICY_ID, REAL_VOICE_STORAGE_BASE],
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
        ($1::uuid, $2::uuid, NULL, NULL, NULL, NULL, NULL, $7::uuid, 'word', 'en_us', 'male', 'google', 'fixture', 'ability-us', 'word', 'mp3', 'audio/mpeg', 'words/lx_ability/word/en_us/male-word-bcffaab67df4.mp3', $8, md5($8), 'generated', now()),
        ($3::uuid, $2::uuid, NULL, NULL, NULL, NULL, NULL, $7::uuid, 'word', 'en_gb', 'female', 'google', 'fixture', 'ability-uk', 'word', 'mp3', 'audio/mpeg', 'words/lx_ability/word/en_gb/female-word-bcffaab67df4.mp3', $8, md5($8), 'generated', now()),
        ($4::uuid, NULL, NULL, NULL, $5::uuid, NULL, NULL, $7::uuid, 'word', 'en_us', 'male', 'google', 'fixture', 'blessing-us', 'word', 'mp3', 'audio/mpeg', 'phrases/ph_a_blessing_in_disguise_73f5c7e2/word/en_us/male-word-6c654557f69d.mp3', $9, md5($9), 'generated', now()),
        ($6::uuid, NULL, NULL, NULL, $5::uuid, NULL, NULL, $7::uuid, 'word', 'en_gb', 'female', 'google', 'fixture', 'blessing-uk', 'word', 'mp3', 'audio/mpeg', 'phrases/ph_a_blessing_in_disguise_73f5c7e2/word/en_gb/female-word-6c654557f69d.mp3', $9, md5($9), 'generated', now())
      ON CONFLICT (storage_policy_id, relative_path)
      DO UPDATE SET
        word_id = EXCLUDED.word_id,
        phrase_entry_id = EXCLUDED.phrase_entry_id,
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
        REAL_WORD_VOICE_US_ID,
        REAL_WORD_ID,
        REAL_WORD_VOICE_UK_ID,
        REAL_PHRASE_VOICE_US_ID,
        REAL_PHRASE_ID,
        REAL_PHRASE_VOICE_UK_ID,
        REAL_VOICE_POLICY_ID,
        REAL_WORD_TEXT,
        REAL_PHRASE_TEXT,
      ],
    );

    await client.query("COMMIT");

    return {
      wordId: REAL_WORD_ID,
      phraseId: REAL_PHRASE_ID,
      wordVoiceUsId: REAL_WORD_VOICE_US_ID,
      wordVoiceUkId: REAL_WORD_VOICE_UK_ID,
      phraseVoiceUsId: REAL_PHRASE_VOICE_US_ID,
      phraseVoiceUkId: REAL_PHRASE_VOICE_UK_ID,
    };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};

export const ensureRealVoiceFixture = async (): Promise<RealVoiceFixture> => {
  if (!fixturePromise) {
    fixturePromise = seedFixture().catch((error) => {
      fixturePromise = null;
      throw error;
    });
  }
  return fixturePromise;
};
