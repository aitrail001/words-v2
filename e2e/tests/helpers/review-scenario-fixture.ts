import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { Client } from "pg";

type EntryType = "word" | "phrase";
type PromptType =
  | "confidence_check"
  | "sentence_gap"
  | "collocation_check"
  | "situation_matching"
  | "entry_to_definition"
  | "audio_to_definition"
  | "typed_recall"
  | "speak_recall"
  | "definition_to_entry";

type ReviewScenarioDefinition = {
  key: string;
  expectedPromptType: PromptType;
  entryType: EntryType;
  entryId: string;
  targetId: string;
  displayText: string;
  normalizedForm: string;
  definition: string;
  sentence: string | null;
  partOfSpeech: string;
  phraseKind?: string;
  browseRank: number;
  bucketStart: number;
  phonetic?: string;
  phonetics?: Record<string, { ipa: string; confidence: number }>;
  withAudio?: boolean;
  lastPromptType?: string;
  usageNote?: string;
  register?: string;
  collocations?: string[];
  synonyms?: string[];
  antonyms?: string[];
  grammarPatterns?: string[];
  cefrLevel?: string | null;
  compiledPayload?: Record<string, unknown>;
  audioRelativePath?: string;
};

type ResolvedReviewScenarioDefinition = ReviewScenarioDefinition & {
  resolvedEntryId: string;
  resolvedTargetId: string;
};

type ReviewQueueSeedStatus = "learning" | "known" | "to_learn";

type ReviewQueueSeedItem = {
  scenarioKey: string;
  status: ReviewQueueSeedStatus;
  dueAt?: Date;
  nextDueAt?: Date;
  dueReviewDate?: string;
  minDueAtUtc?: Date;
  recheckDueAt?: Date | null;
  lastReviewedAt?: Date | null;
  srsBucket?: "1d" | "2d" | "3d" | "5d" | "7d" | "14d" | "30d" | "90d" | "180d";
};

export type DueReviewSeedFixture = {
  displayText: string;
  definition: string;
};

type SeedCustomReviewQueueOptions = {
  timezone?: string;
  items: readonly ReviewQueueSeedItem[];
};

export type ReviewScenarioStateSnapshot = {
  queueItemId: string;
  dueReviewDate: string | null;
  minDueAtUtc: string | null;
  nextDueAt: string | null;
  recheckDueAt: string | null;
  lastReviewedAt: string | null;
  lastOutcome: string | null;
};

export type GroupedReviewQueueFixture = {
  dueNowText: string;
  dueNowDefinition: string;
  tomorrowText: string;
  hiddenKnownText: string;
  hiddenToLearnText: string;
  effectiveNow: string;
};

export type FailedReviewQueueFixture = {
  failedText: string;
  futureText: string;
};

export type LongHorizonReviewFixture = {
  reviewText: string;
};

export type AdminTimeTravelReviewFixture = {
  futureText: string;
  effectiveNow: string;
};

export type EntryDetailNullScheduleFixture = {
  entryType: EntryType;
  entryId: string;
  displayText: string;
  expectedScheduleLabel: string;
};

export type LegacyDuplicateReviewQueueFixture = {
  bucket: "1d";
  visibleTexts: [string, string];
};

function resolveDataRoot(): string {
  const candidates = [
    process.env.E2E_WORDS_DATA_ROOT,
    path.resolve(__dirname, "../../../../../data"),
    "/workspace/data",
    path.resolve(__dirname, "../../../../data"),
    "/workspace/data",
  ].filter((value): value is string => Boolean(value));

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return candidates[1] ?? candidates[0]!;
}

const DATA_ROOT = resolveDataRoot();
const WORD_POLICY_ID = "6c19a4f5-5970-4d94-8af8-728e4433c200";
const DEFINITION_POLICY_ID = "f1ecf376-96d1-4212-b235-fd3963e2f2bb";
const REVIEW_SCENARIO_AUDIO_ROOT = path.join(DATA_ROOT, "lexicon/voice");
const REVIEW_SCENARIO_AUDIO_CONTAINER_ROOT = "/app/data/lexicon/voice";
const REVIEW_SCENARIO_AUDIO_DIR = path.join(
  DATA_ROOT,
  "lexicon/voice/phrases-7488-20260323-reviewed-phrasals-idioms-v1",
);
const REVIEW_SCENARIO_AUDIO_RELATIVE_PATH =
  "ph_as_it_is_eb09baab/word/en_us/female-word-f5c9477a85fc.mp3";
const WORDS_SNAPSHOT_PATH = path.join(
  DATA_ROOT,
  "lexicon/snapshots/words-40000-20260323-main-wordfreq-live-target30k/reviewed/approved.jsonl",
);
const PHRASES_SNAPSHOT_PATH = path.join(
  DATA_ROOT,
  "lexicon/snapshots/phrases-7488-20260323-reviewed-phrasals-idioms-v1/reviewed/approved.jsonl",
);

type ScenarioSpec = {
  key: string;
  expectedPromptType: PromptType;
  entryType: EntryType;
  entryId: string;
  targetId: string;
  snapshotWord: string;
  browseRank: number;
  bucketStart: number;
  withAudio?: boolean;
  lastPromptType?: string;
  audioRelativePath?: string;
};

type SnapshotSense = {
  pos: string;
  definition: string;
  examples?: Array<{ sentence: string }>;
  usage_note?: string;
  register?: string;
  collocations?: string[];
  synonyms?: string[];
  antonyms?: string[];
  grammar_patterns?: string[];
};

type SnapshotRow = {
  word: string;
  display_form?: string;
  normalized_form?: string;
  phonetics?: Record<string, { ipa: string; confidence: number }>;
  phrase_kind?: string;
  cefr_level?: string;
  senses: SnapshotSense[];
};

const FALLBACK_WORD_ROWS: Record<string, SnapshotRow> = {
  persistence: {
    word: "persistence",
    normalized_form: "persistence",
    display_form: "persistence",
    cefr_level: "B2",
    phonetics: { us: { ipa: "/pərˈsɪstəns/", confidence: 0.9 } },
    senses: [{ pos: "noun", definition: "continued effort despite difficulty", examples: [{ sentence: "Persistence helped her finish the project despite repeated setbacks." }] }],
  },
  barely: {
    word: "barely",
    normalized_form: "barely",
    display_form: "barely",
    cefr_level: "B1",
    phonetics: { us: { ipa: "/ˈberli/", confidence: 0.9 } },
    senses: [{ pos: "adverb", definition: "only just; by a very small amount", examples: [{ sentence: "He barely caught the train before the doors closed." }] }],
  },
  resilience: {
    word: "resilience",
    normalized_form: "resilience",
    display_form: "resilience",
    cefr_level: "B2",
    phonetics: { us: { ipa: "/rɪˈzɪliəns/", confidence: 0.9 } },
    senses: [{ pos: "noun", definition: "the ability to recover quickly from difficulties", examples: [{ sentence: "Her resilience helped her recover after the company restructured." }] }],
  },
  meticulous: {
    word: "meticulous",
    normalized_form: "meticulous",
    display_form: "meticulous",
    cefr_level: "C1",
    phonetics: { us: { ipa: "/məˈtɪkjələs/", confidence: 0.9 } },
    senses: [{ pos: "adjective", definition: "very careful and precise", examples: [{ sentence: "The editor was meticulous about punctuation and formatting." }] }],
  },
  candid: {
    word: "candid",
    normalized_form: "candid",
    display_form: "candid",
    cefr_level: "C1",
    phonetics: { us: { ipa: "/ˈkændɪd/", confidence: 0.9 } },
    senses: [{ pos: "adjective", definition: "honest and direct", examples: [{ sentence: "She gave a candid answer about the project risks." }] }],
  },
  candidate: {
    word: "candidate",
    normalized_form: "candidate",
    display_form: "candidate",
    cefr_level: "B1",
    phonetics: { us: { ipa: "/ˈkændɪdeɪt/", confidence: 0.9 } },
    senses: [{ pos: "noun", definition: "a person being considered for a role or position", examples: [{ sentence: "The candidate presented a strong plan during the interview." }] }],
  },
};

const FALLBACK_PHRASE_ROWS: Record<string, SnapshotRow> = {
  "jump the gun": {
    word: "jump the gun",
    normalized_form: "jump the gun",
    display_form: "jump the gun",
    phrase_kind: "idiom",
    senses: [{ pos: "phrase", definition: "to do something too early", examples: [{ sentence: "I think we may be moving too fast by announcing it before testing is complete." }] }],
  },
  "as it is": {
    word: "as it is",
    normalized_form: "as it is",
    display_form: "as it is",
    phrase_kind: "phrase",
    senses: [{ pos: "phrase", definition: "in the current state without changes", examples: [{ sentence: "The report is clear enough as it is." }] }],
  },
  "by and large": {
    word: "by and large",
    normalized_form: "by and large",
    display_form: "by and large",
    phrase_kind: "idiom",
    senses: [{ pos: "phrase", definition: "generally; on the whole", examples: [{ sentence: "By and large, the rollout went as planned." }] }],
  },
};

const SCENARIO_SPECS: readonly ScenarioSpec[] = [
  { key: "confidence-check", expectedPromptType: "confidence_check", entryType: "word", entryId: "81000000-0000-0000-0000-000000000001", targetId: "82000000-0000-0000-0000-000000000001", snapshotWord: "persistence", browseRank: 3101, bucketStart: 3101, withAudio: true, audioRelativePath: "words-40000-20260323-main-wordfreq-live-target30k/lx_persistence/word/en_us/female-word-0d2a4d0e13a3.mp3" },
  { key: "sentence-gap", expectedPromptType: "sentence_gap", entryType: "word", entryId: "81000000-0000-0000-0000-000000000011", targetId: "82000000-0000-0000-0000-000000000011", snapshotWord: "barely", browseRank: 3102, bucketStart: 3101 },
  { key: "collocation", expectedPromptType: "collocation_check", entryType: "phrase", entryId: "81000000-0000-0000-0000-000000000002", targetId: "82000000-0000-0000-0000-000000000002", snapshotWord: "jump the gun", browseRank: 3103, bucketStart: 3101, lastPromptType: "sentence_gap" },
  { key: "situation", expectedPromptType: "situation_matching", entryType: "word", entryId: "81000000-0000-0000-0000-000000000003", targetId: "82000000-0000-0000-0000-000000000003", snapshotWord: "resilience", browseRank: 3104, bucketStart: 3101 },
  { key: "entry-to-definition", expectedPromptType: "entry_to_definition", entryType: "word", entryId: "81000000-0000-0000-0000-000000000004", targetId: "82000000-0000-0000-0000-000000000004", snapshotWord: "meticulous", browseRank: 3105, bucketStart: 3101 },
  { key: "audio-to-definition", expectedPromptType: "audio_to_definition", entryType: "phrase", entryId: "81000000-0000-0000-0000-000000000005", targetId: "82000000-0000-0000-0000-000000000005", snapshotWord: "as it is", browseRank: 3106, bucketStart: 3101, withAudio: true, audioRelativePath: "phrases-7488-20260323-reviewed-phrasals-idioms-v1/ph_as_it_is_eb09baab/word/en_us/female-word-f5c9477a85fc.mp3" },
  { key: "typed-recall", expectedPromptType: "typed_recall", entryType: "word", entryId: "81000000-0000-0000-0000-000000000006", targetId: "82000000-0000-0000-0000-000000000006", snapshotWord: "candid", browseRank: 3107, bucketStart: 3101 },
  { key: "speak-recall", expectedPromptType: "speak_recall", entryType: "word", entryId: "81000000-0000-0000-0000-000000000010", targetId: "82000000-0000-0000-0000-000000000010", snapshotWord: "candidate", browseRank: 3108, bucketStart: 3101, withAudio: true, audioRelativePath: "words-40000-20260323-main-wordfreq-live-target30k/lx_candidate/word/en_us/female-word-dda18a0e21ae.mp3" },
  { key: "definition-to-entry", expectedPromptType: "definition_to_entry", entryType: "phrase", entryId: "81000000-0000-0000-0000-000000000009", targetId: "82000000-0000-0000-0000-000000000009", snapshotWord: "by and large", browseRank: 3109, bucketStart: 3101 },
] as const;

const loadSnapshotEntries = (
  snapshotPath: string,
  fallbackEntries: Record<string, SnapshotRow>,
): Record<string, SnapshotRow> => {
  if (!fs.existsSync(snapshotPath)) {
    return fallbackEntries;
  }
  const entries: Record<string, SnapshotRow> = {};
  const lines = fs.readFileSync(snapshotPath, "utf8").trim().split("\n");
  for (const line of lines) {
    const row = JSON.parse(line) as SnapshotRow;
    entries[row.word] = row;
  }
  return entries;
};

const choosePrimaryPhonetic = (
  phonetics?: Record<string, { ipa: string; confidence: number }>,
): string | undefined => {
  if (!phonetics) {
    return undefined;
  }
  for (const locale of ["us", "uk", "au"]) {
    const candidate = phonetics[locale]?.ipa;
    if (candidate) {
      return candidate;
    }
  }
  return Object.values(phonetics)[0]?.ipa;
};

const buildScenarioDefinitions = (): readonly ReviewScenarioDefinition[] => {
  const wordRows = loadSnapshotEntries(WORDS_SNAPSHOT_PATH, FALLBACK_WORD_ROWS);
  const phraseRows = loadSnapshotEntries(PHRASES_SNAPSHOT_PATH, FALLBACK_PHRASE_ROWS);
  return SCENARIO_SPECS.map((spec) => {
    const row = spec.entryType === "word" ? wordRows[spec.snapshotWord] : phraseRows[spec.snapshotWord];
    const sense = row.senses[0];
    const sentence = sense.examples?.[0]?.sentence ?? null;
    return {
      key: spec.key,
      expectedPromptType: spec.expectedPromptType,
      entryType: spec.entryType,
      entryId: spec.entryId,
      targetId: spec.targetId,
      displayText: row.display_form ?? row.word,
      normalizedForm: row.normalized_form ?? row.word.toLowerCase(),
      definition: sense.definition,
      sentence,
      partOfSpeech: sense.pos,
      phraseKind: row.phrase_kind,
      browseRank: spec.browseRank,
      bucketStart: spec.bucketStart,
      phonetic: choosePrimaryPhonetic(row.phonetics),
      phonetics: row.phonetics,
      usageNote: sense.usage_note,
      register: sense.register ?? "neutral",
      collocations: sense.collocations ?? [],
      synonyms: sense.synonyms ?? [],
      antonyms: sense.antonyms ?? [],
      grammarPatterns: sense.grammar_patterns ?? [],
      cefrLevel: row.cefr_level ?? null,
      compiledPayload: spec.entryType === "phrase" ? (row as unknown as Record<string, unknown>) : undefined,
      withAudio: spec.withAudio,
      lastPromptType: spec.lastPromptType,
      audioRelativePath: spec.audioRelativePath,
    };
  });
};

export const REVIEW_SCENARIO_DEFINITIONS: readonly ReviewScenarioDefinition[] =
  buildScenarioDefinitions();

type DbConfig =
  | { connectionString: string }
  | {
      host: string;
      port: number;
      user: string;
      password: string;
      database: string;
    };

const inferDbHost = (): string => {
  const apiUrl = process.env.E2E_API_URL ?? "";
  return apiUrl.includes("://backend:") ? "postgres" : "localhost";
};

const getDbConfigs = (): DbConfig[] => {
  const connectionString = process.env.E2E_DB_URL;
  if (connectionString) {
    return [{ connectionString }];
  }

  const configuredPassword = process.env.E2E_DB_PASSWORD;
  const passwordCandidates = Array.from(
    new Set(
      [configuredPassword, "change_this_password_in_production", "devpassword"].filter(
        (value): value is string => Boolean(value),
      ),
    ),
  );

  return passwordCandidates.map((password) => ({
    host: process.env.E2E_DB_HOST ?? inferDbHost(),
    port: Number(process.env.E2E_DB_PORT ?? 5432),
    user: process.env.E2E_DB_USER ?? "vocabapp",
    password,
    database: process.env.E2E_DB_NAME ?? process.env.DEV_DB_NAME ?? "vocabapp_dev_full",
  }));
};

const connectClient = async (): Promise<Client> => {
  let lastError: unknown = null;
  for (const config of getDbConfigs()) {
    const client = new Client(config);
    try {
      await client.connect();
      return client;
    } catch (error) {
      lastError = error;
      await client.end().catch(() => undefined);
    }
  }
  throw lastError ?? new Error("Unable to connect to Postgres with known E2E DB configs.");
};

const hashText = (value: string): string =>
  createHash("sha256").update(value, "utf8").digest("hex");

const ensureReviewScenarioAudioFixture = async (): Promise<void> => {
  const fs = await import("node:fs/promises");
  const fixtureBytes = Buffer.from("ID3review-fixture-audio");
  const ensureFile = async (targetPath: string) => {
    try {
      await fs.access(targetPath);
    } catch {
      await fs.mkdir(path.dirname(targetPath), { recursive: true });
      await fs.writeFile(targetPath, fixtureBytes);
    }
  };

  try {
    await ensureFile(path.join(REVIEW_SCENARIO_AUDIO_DIR, REVIEW_SCENARIO_AUDIO_RELATIVE_PATH));
    for (const scenario of REVIEW_SCENARIO_DEFINITIONS) {
      if (!scenario.withAudio || !scenario.audioRelativePath) {
        continue;
      }
      await ensureFile(path.join(REVIEW_SCENARIO_AUDIO_ROOT, scenario.audioRelativePath));
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (
      message.includes("ENOTDIR")
      || message.includes("ENOENT")
      || message.includes("EACCES")
    ) {
      return;
    }
    throw error;
  }
};

let catalogSeedPromise: Promise<ResolvedReviewScenarioDefinition[]> | null = null;

const ensureVoicePolicies = async (
  client: Client,
): Promise<{ wordPolicyId: string; definitionPolicyId: string }> => {
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
    VALUES
      (
        $1::uuid,
        'word_default',
        'global',
        'word',
        'default',
        'default',
        'all',
        'local',
        $2,
        'local',
        $3,
        now()
      ),
      (
        $4::uuid,
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
    `,
    [
      WORD_POLICY_ID,
      REVIEW_SCENARIO_AUDIO_CONTAINER_ROOT,
      REVIEW_SCENARIO_AUDIO_ROOT,
      DEFINITION_POLICY_ID,
    ],
  );
  const policyResult = await client.query<{ policy_key: string; id: string }>(
    `
    SELECT policy_key, id::text AS id
    FROM lexicon.lexicon_voice_storage_policies
    WHERE policy_key IN ('word_default', 'definition_default')
    `,
  );
  const wordPolicyId =
    policyResult.rows.find((row) => row.policy_key === "word_default")?.id ?? WORD_POLICY_ID;
  const definitionPolicyId =
    policyResult.rows.find((row) => row.policy_key === "definition_default")?.id ?? DEFINITION_POLICY_ID;
  return { wordPolicyId, definitionPolicyId };
};

const upsertWordScenario = async (
  client: Client,
  scenario: ReviewScenarioDefinition,
): Promise<ResolvedReviewScenarioDefinition> => {
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
      $5,
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
      scenario.entryId,
      scenario.displayText,
      JSON.stringify(scenario.phonetics ?? {}),
      scenario.phonetic ?? null,
      scenario.browseRank,
    ],
  );
  const resolvedEntryId = wordResult.rows[0]?.id ?? scenario.entryId;

  await client.query(`DELETE FROM lexicon.word_part_of_speech WHERE word_id = $1::uuid`, [
    resolvedEntryId,
  ]);
  await client.query(
    `
    INSERT INTO lexicon.word_part_of_speech (id, word_id, value, order_index, created_at)
    VALUES ($1::uuid, $2::uuid, $3, 0, now())
    `,
    [randomUUID(), resolvedEntryId, scenario.partOfSpeech],
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
      $4,
      $5,
      0,
      'snapshot-approved-review-seed',
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
      scenario.targetId,
      resolvedEntryId,
      scenario.definition,
      scenario.partOfSpeech,
      scenario.sentence,
    ],
  );

  if (scenario.sentence) {
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
        'snapshot-approved-review-seed',
        now()
      )
      ON CONFLICT (meaning_id, sentence)
      DO UPDATE SET
        difficulty = EXCLUDED.difficulty,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      `,
      [randomUUID(), scenario.targetId, scenario.sentence],
    );
  }
  return {
    ...scenario,
    resolvedEntryId,
    resolvedTargetId: scenario.targetId,
  };
};

const upsertPhraseScenario = async (
  client: Client,
  scenario: ReviewScenarioDefinition,
): Promise<ResolvedReviewScenarioDefinition> => {
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
      $4,
      'en',
      $5,
      $6::jsonb,
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
      scenario.entryId,
      scenario.displayText,
      scenario.normalizedForm,
      scenario.phraseKind ?? "multiword_expression",
      scenario.cefrLevel ?? "B2",
      JSON.stringify(scenario.compiledPayload ?? {}),
    ],
  );
  const resolvedEntryId = phraseResult.rows[0]?.id ?? scenario.entryId;

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
      $3,
      $4,
      $5,
      $6,
      'general',
      '[]'::jsonb,
      $7::jsonb,
      $8::jsonb,
      $9::jsonb,
      $10::jsonb,
      0,
      now()
    )
    ON CONFLICT (phrase_entry_id, order_index)
    DO UPDATE SET
      definition = EXCLUDED.definition,
      part_of_speech = EXCLUDED.part_of_speech,
      register = EXCLUDED.register,
      primary_domain = EXCLUDED.primary_domain,
      secondary_domains = EXCLUDED.secondary_domains,
      grammar_patterns = EXCLUDED.grammar_patterns,
      synonyms = EXCLUDED.synonyms,
      antonyms = EXCLUDED.antonyms,
      collocations = EXCLUDED.collocations
    RETURNING id::text AS id
    `,
    [
      scenario.targetId,
      resolvedEntryId,
      scenario.definition,
      scenario.usageNote ?? null,
      scenario.partOfSpeech,
      scenario.register ?? "neutral",
      JSON.stringify(scenario.grammarPatterns ?? []),
      JSON.stringify(scenario.synonyms ?? []),
      JSON.stringify(scenario.antonyms ?? []),
      JSON.stringify(scenario.collocations ?? []),
    ],
  );
  const resolvedTargetId = phraseSenseResult.rows[0]?.id ?? scenario.targetId;

  if (scenario.sentence) {
    await client.query(
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
        $3,
        'B2',
        0,
        'snapshot-approved-review-seed',
        now()
      )
      ON CONFLICT (phrase_sense_id, sentence)
      DO UPDATE SET
        difficulty = EXCLUDED.difficulty,
        order_index = EXCLUDED.order_index,
        source = EXCLUDED.source
      `,
      [randomUUID(), resolvedTargetId, scenario.sentence],
    );
  }
  return {
    ...scenario,
    resolvedEntryId,
    resolvedTargetId,
  };
};

const upsertCatalogEntry = async (
  client: Client,
  scenario: ResolvedReviewScenarioDefinition,
): Promise<void> => {
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
      $1,
      $2::uuid,
      $3,
      $4,
      $5,
      $6,
      $7,
      $8,
      $9,
      $10,
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
    [
      scenario.entryType,
      scenario.resolvedEntryId,
      scenario.displayText,
      scenario.normalizedForm,
      scenario.browseRank,
      scenario.bucketStart,
      scenario.cefrLevel ?? "B2",
      scenario.entryType === "word" ? scenario.partOfSpeech : null,
      scenario.entryType === "phrase" ? scenario.phraseKind ?? "multiword_expression" : null,
      scenario.entryType === "word",
    ],
  );
};

const seedScenarioCatalog = async (): Promise<ResolvedReviewScenarioDefinition[]> => {
  await ensureReviewScenarioAudioFixture();
  const client = await connectClient();
  try {
    await client.query("BEGIN");
    const policies = await ensureVoicePolicies(client);
    const resolvedScenarios: ResolvedReviewScenarioDefinition[] = [];
    for (const scenario of REVIEW_SCENARIO_DEFINITIONS) {
      const resolvedScenario =
        scenario.entryType === "word"
          ? await upsertWordScenario(client, scenario)
          : await upsertPhraseScenario(client, scenario);
      resolvedScenarios.push(resolvedScenario);
      await upsertCatalogEntry(client, resolvedScenario);
    }
    for (const audioScenario of resolvedScenarios.filter((item) => item.withAudio && item.audioRelativePath)) {
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
        VALUES (
          $1::uuid,
          $2::uuid,
          NULL,
          NULL,
          $3::uuid,
          NULL,
          NULL,
          $4::uuid,
          'word',
          'en_us',
          'female',
          'default',
          'default',
          'fixture-voice',
          'word',
          'mp3',
          'audio/mpeg',
          $5,
          $6,
          $7,
          'generated',
          now()
        )
        ON CONFLICT (storage_policy_id, relative_path)
        DO UPDATE SET
          word_id = EXCLUDED.word_id,
          meaning_id = EXCLUDED.meaning_id,
          meaning_example_id = EXCLUDED.meaning_example_id,
          phrase_entry_id = EXCLUDED.phrase_entry_id,
          phrase_sense_id = EXCLUDED.phrase_sense_id,
          phrase_sense_example_id = EXCLUDED.phrase_sense_example_id,
          content_scope = EXCLUDED.content_scope,
          locale = EXCLUDED.locale,
          voice_role = EXCLUDED.voice_role,
          provider = EXCLUDED.provider,
          family = EXCLUDED.family,
          voice_id = EXCLUDED.voice_id,
          profile_key = EXCLUDED.profile_key,
          source_text = EXCLUDED.source_text,
          source_text_hash = EXCLUDED.source_text_hash,
          audio_format = EXCLUDED.audio_format,
          mime_type = EXCLUDED.mime_type,
          status = EXCLUDED.status
        `,
        [
          randomUUID(),
          audioScenario.entryType === "word" ? audioScenario.resolvedEntryId : null,
          audioScenario.entryType === "phrase" ? audioScenario.resolvedEntryId : null,
          policies.wordPolicyId,
          audioScenario.audioRelativePath,
          audioScenario.displayText,
          hashText(audioScenario.displayText),
        ],
      );
    }
    await client.query("COMMIT");
    return resolvedScenarios;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};

const ensureScenarioCatalog = async (): Promise<ResolvedReviewScenarioDefinition[]> => {
  if (!catalogSeedPromise) {
    catalogSeedPromise = seedScenarioCatalog().catch((error) => {
      catalogSeedPromise = null;
      throw error;
    });
  }
  return await catalogSeedPromise;
};

const upsertUserPreferences = async (
  client: Client,
  userId: string,
  timezone = "UTC",
): Promise<void> => {
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
    VALUES ($1::uuid, $2::uuid, 'us', 'es', 'cards', 'balanced', $3, true, true, true, false)
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
    [randomUUID(), userId, timezone],
  );
};

const upsertLearnerStatus = async (
  client: Client,
  userId: string,
  scenario: ResolvedReviewScenarioDefinition,
  status: ReviewQueueSeedStatus,
): Promise<void> => {
  await client.query(
    `
    INSERT INTO learner_entry_statuses (id, user_id, entry_type, entry_id, status)
    VALUES ($1::uuid, $2::uuid, $3, $4::uuid, $5)
    ON CONFLICT (user_id, entry_type, entry_id)
    DO UPDATE SET status = EXCLUDED.status, updated_at = now()
    `,
    [randomUUID(), userId, scenario.entryType, scenario.resolvedEntryId, status],
  );
};

const insertReviewQueueState = async (
  client: Client,
  userId: string,
  scenario: ResolvedReviewScenarioDefinition,
  item: ReviewQueueSeedItem,
  timezone = "UTC",
): Promise<void> => {
  if (Boolean(item.dueReviewDate) !== Boolean(item.minDueAtUtc)) {
    throw new Error(
      `Scenario ${item.scenarioKey} must provide both dueReviewDate and minDueAtUtc together.`,
    );
  }

  const minDueAtUtc = item.minDueAtUtc ?? item.nextDueAt ?? item.dueAt ?? null;
  if (minDueAtUtc === null) {
    throw new Error(`Scenario ${item.scenarioKey} is missing a due timestamp.`);
  }

  const dueReviewDate =
    item.dueReviewDate ??
    new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(minDueAtUtc);

  const createdAt = new Date(minDueAtUtc.getTime() - 3_600_000);
  const reviewedAt = item.lastReviewedAt ?? new Date(minDueAtUtc.getTime() - 86_400_000);
  const srsBucket = item.srsBucket ?? "1d";
  const cadenceStep = {
    "1d": 0,
    "2d": 1,
    "3d": 2,
    "5d": 0,
    "7d": 1,
    "14d": 2,
    "30d": 0,
    "90d": 1,
    "180d": 2,
  }[srsBucket];
  const intervalDays = {
    "1d": 1,
    "2d": 2,
    "3d": 3,
    "5d": 5,
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
    "180d": 180,
  }[srsBucket];
  await client.query(
    `
    INSERT INTO entry_review_states (
      id,
      user_id,
      target_type,
      target_id,
      entry_type,
      entry_id,
      stability,
      difficulty,
      success_streak,
      lapse_count,
      exposure_count,
      times_remembered,
      srs_bucket,
      cadence_step,
      last_prompt_type,
      last_submission_prompt_id,
      last_outcome,
      is_fragile,
      is_suspended,
      relearning,
      relearning_trigger,
      recheck_due_at,
      last_reviewed_at,
      due_review_date,
      min_due_at_utc,
      created_at,
      updated_at
    )
    VALUES (
      $1::uuid,
      $2::uuid,
      $3,
      $4::uuid,
      $5,
      $6::uuid,
      $7,
      0.45,
      0,
      0,
      0,
      0,
      $8,
      $9,
      $10,
      $11,
      NULL,
      false,
      false,
      false,
      NULL,
      $12::timestamptz,
      $13::timestamptz,
      $14::date,
      $15::timestamptz,
      $16::timestamptz,
      $16::timestamptz
    )
    `,
    [
      randomUUID(),
      userId,
      scenario.entryType === "word" ? "meaning" : "phrase_sense",
      scenario.resolvedTargetId,
      scenario.entryType,
      scenario.resolvedEntryId,
      intervalDays,
      srsBucket,
      cadenceStep,
      scenario.lastPromptType ?? null,
      `manual_prompt_type:${scenario.expectedPromptType}`,
      item.recheckDueAt?.toISOString() ?? null,
      reviewedAt.toISOString(),
      dueReviewDate,
      minDueAtUtc.toISOString(),
      createdAt.toISOString(),
    ],
  );
};

export const seedCustomReviewQueue = async (
  userId: string,
  options: SeedCustomReviewQueueOptions,
): Promise<Record<string, ResolvedReviewScenarioDefinition>> => {
  const { timezone = "UTC", items } = options;
  const resolvedScenarios = await ensureScenarioCatalog();
  const scenarioMap = new Map(resolvedScenarios.map((scenario) => [scenario.key, scenario]));
  const client = await connectClient();

  try {
    await client.query("BEGIN");
    await upsertUserPreferences(client, userId, timezone);
    await client.query(`DELETE FROM entry_review_states WHERE user_id = $1::uuid`, [userId]);

    for (const item of items) {
      const scenario = scenarioMap.get(item.scenarioKey);
      if (!scenario) {
        throw new Error(`Missing review scenario definition for ${item.scenarioKey}`);
      }
      await upsertLearnerStatus(client, userId, scenario, item.status);
      if (item.status === "learning") {
        await insertReviewQueueState(client, userId, scenario, item, timezone);
      }
    }

    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }

  return Object.fromEntries(items.map((item) => [item.scenarioKey, scenarioMap.get(item.scenarioKey)!]));
};

export const seedDueReviewScenarioItem = async (
  userId: string,
  scenarioKey = "entry-to-definition",
): Promise<DueReviewSeedFixture> => {
  const now = new Date();
  const scenarios = await seedCustomReviewQueue(userId, {
    items: [
      {
        scenarioKey,
        status: "learning",
        dueAt: new Date(now.getTime() - 60_000),
        lastReviewedAt: new Date(now.getTime() - 24 * 60 * 60 * 1000),
        srsBucket: "1d",
      },
    ],
  });
  const scenario = scenarios[scenarioKey];
  if (!scenario) {
    throw new Error(`Missing due review scenario for ${scenarioKey}`);
  }
  return {
    displayText: scenario.displayText,
    definition: scenario.definition,
  };
};

export const seedReviewScenarioQueue = async (userId: string): Promise<void> => {
  const resolvedScenarios = await ensureScenarioCatalog();

  const client = await connectClient();

  try {
    await client.query("BEGIN");

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
      VALUES ($1::uuid, $2::uuid, 'us', 'es', 'cards', 'balanced', 'UTC', false, true, true, false)
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

    await client.query(`DELETE FROM entry_review_states WHERE user_id = $1::uuid`, [userId]);

    for (const scenario of resolvedScenarios) {
      await client.query(
        `
        INSERT INTO learner_entry_statuses (id, user_id, entry_type, entry_id, status)
        VALUES ($1::uuid, $2::uuid, $3, $4::uuid, 'learning')
        ON CONFLICT (user_id, entry_type, entry_id)
        DO UPDATE SET status = EXCLUDED.status, updated_at = now()
        `,
        [randomUUID(), userId, scenario.entryType, scenario.resolvedEntryId],
      );
    }

    const baseTs = Date.parse("2024-01-01T00:00:00.000Z");
    for (const [index, scenario] of resolvedScenarios.entries()) {
      await client.query(
        `
        INSERT INTO entry_review_states (
          id,
          user_id,
          target_type,
          target_id,
          entry_type,
          entry_id,
          stability,
          difficulty,
          success_streak,
          lapse_count,
          exposure_count,
          times_remembered,
          last_prompt_type,
          last_submission_prompt_id,
          last_outcome,
          is_fragile,
          is_suspended,
          relearning,
          relearning_trigger,
          recheck_due_at,
          last_reviewed_at,
          next_due_at,
          created_at,
          updated_at
        )
        VALUES (
          $1::uuid,
          $2::uuid,
          $3,
          $4::uuid,
          $5,
          $6::uuid,
          2.0,
          0.45,
          0,
          0,
          0,
          0,
          $7,
          $8,
          NULL,
          false,
          false,
          false,
          NULL,
          NULL,
          NULL,
          $9::timestamptz,
          $10::timestamptz,
          $10::timestamptz
        )
        `,
        [
          randomUUID(),
          userId,
          scenario.entryType === "word" ? "meaning" : "phrase_sense",
          scenario.resolvedTargetId,
          scenario.entryType,
          scenario.resolvedEntryId,
          scenario.lastPromptType ?? null,
          `manual_prompt_type:${scenario.expectedPromptType}`,
          new Date(baseTs + index * 1000).toISOString(),
          new Date(baseTs + index * 1000).toISOString(),
        ],
      );
    }

    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};

export const seedGroupedReviewQueueFixture = async (
  userId: string,
): Promise<GroupedReviewQueueFixture> => {
  const now = new Date();
  const dueNowAt = new Date(now.getTime() - 60_000);
  const tomorrowAt = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + 1,
      9,
      0,
      0,
      0,
    ),
  );
  const oneToThreeMonthsAt = new Date(now.getTime() + 45 * 24 * 60 * 60 * 1000);
  const sixPlusMonthsAt = new Date(now.getTime() + 220 * 24 * 60 * 60 * 1000);

  const scenarios = await seedCustomReviewQueue(userId, {
    items: [
    {
      scenarioKey: "entry-to-definition",
      status: "learning",
      dueAt: dueNowAt,
      lastReviewedAt: new Date(now.getTime() - 24 * 60 * 60 * 1000),
      srsBucket: "1d",
    },
    {
      scenarioKey: "definition-to-entry",
      status: "learning",
      dueAt: tomorrowAt,
      lastReviewedAt: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000),
      srsBucket: "7d",
    },
    {
      scenarioKey: "situation",
      status: "learning",
      dueAt: oneToThreeMonthsAt,
      lastReviewedAt: new Date(now.getTime() - 4 * 24 * 60 * 60 * 1000),
      srsBucket: "30d",
    },
    {
      scenarioKey: "collocation",
      status: "learning",
      dueAt: sixPlusMonthsAt,
      lastReviewedAt: new Date(now.getTime() - 8 * 24 * 60 * 60 * 1000),
      srsBucket: "180d",
    },
    { scenarioKey: "typed-recall", status: "known" },
    { scenarioKey: "sentence-gap", status: "to_learn" },
    ],
  });

  return {
    dueNowText: scenarios["entry-to-definition"].displayText,
    dueNowDefinition: scenarios["entry-to-definition"].definition,
    tomorrowText: scenarios["definition-to-entry"].displayText,
    hiddenKnownText: scenarios["typed-recall"].displayText,
    hiddenToLearnText: scenarios["sentence-gap"].displayText,
    effectiveNow: new Date(tomorrowAt.getTime() + 60_000).toISOString(),
  };
};

export const seedFailedReviewQueueFixture = async (
  userId: string,
): Promise<FailedReviewQueueFixture> => {
  const now = new Date();
  const dueNowAt = new Date(now.getTime() - 60_000);
  const tomorrowAt = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + 1,
      9,
      0,
      0,
      0,
    ),
  );

  const scenarios = await seedCustomReviewQueue(userId, {
    items: [
    {
      scenarioKey: "sentence-gap",
      status: "learning",
      dueAt: dueNowAt,
      lastReviewedAt: new Date(now.getTime() - 24 * 60 * 60 * 1000),
      srsBucket: "1d",
    },
    {
      scenarioKey: "definition-to-entry",
      status: "learning",
      dueAt: tomorrowAt,
      lastReviewedAt: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000),
      srsBucket: "7d",
    },
    ],
  });

  return {
    failedText: scenarios["sentence-gap"].displayText,
    futureText: scenarios["definition-to-entry"].displayText,
  };
};

export const seedLongHorizonReviewFixture = async (
  userId: string,
): Promise<LongHorizonReviewFixture> => {
  const now = new Date();
  const longHorizonAt = new Date(now.getTime() + 120 * 24 * 60 * 60 * 1000);

  const scenarios = await seedCustomReviewQueue(userId, {
    items: [
    {
      scenarioKey: "typed-recall",
      status: "learning",
      dueAt: longHorizonAt,
      lastReviewedAt: now,
      srsBucket: "180d",
    },
    ],
  });

  return {
    reviewText: scenarios["typed-recall"].displayText,
  };
};

export const seedAdminTimeTravelReviewFixture = async (
  userId: string,
): Promise<AdminTimeTravelReviewFixture> => {
  const now = new Date();
  const tomorrowAt = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + 1,
      9,
      0,
      0,
      0,
    ),
  );
  const laterAt = new Date(now.getTime() + 45 * 24 * 60 * 60 * 1000);

  const scenarios = await seedCustomReviewQueue(userId, {
    items: [
    {
      scenarioKey: "definition-to-entry",
      status: "learning",
      dueAt: tomorrowAt,
      lastReviewedAt: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000),
      srsBucket: "7d",
    },
    {
      scenarioKey: "situation",
      status: "learning",
      dueAt: laterAt,
      lastReviewedAt: new Date(now.getTime() - 4 * 24 * 60 * 60 * 1000),
      srsBucket: "30d",
    },
    ],
  });

  return {
    futureText: scenarios["definition-to-entry"].displayText,
    effectiveNow: new Date(tomorrowAt.getTime() + 60_000).toISOString(),
  };
};

export const seedEntryDetailNullScheduleFixture = async (
  userId: string,
): Promise<EntryDetailNullScheduleFixture> => {
  const resolvedScenarios = await ensureScenarioCatalog();
  const scenario = resolvedScenarios.find((item) => item.key === "entry-to-definition");
  if (!scenario) {
    throw new Error("Missing review scenario definition for entry-to-definition");
  }

  const client = await connectClient();
  try {
    await client.query("BEGIN");
    await upsertUserPreferences(client, userId);
    await client.query(`DELETE FROM entry_review_states WHERE user_id = $1::uuid`, [userId]);
    await upsertLearnerStatus(client, userId, scenario, "learning");
    await client.query(
      `
      INSERT INTO entry_review_states (
        id,
        user_id,
        target_type,
        target_id,
        entry_type,
        entry_id,
        stability,
        difficulty,
        success_streak,
        lapse_count,
        exposure_count,
        times_remembered,
        srs_bucket,
        cadence_step,
        last_prompt_type,
        last_submission_prompt_id,
        last_outcome,
        is_fragile,
        is_suspended,
        relearning,
        relearning_trigger,
        recheck_due_at,
        last_reviewed_at,
        next_due_at,
        created_at,
        updated_at
      )
      VALUES (
        $1::uuid,
        $2::uuid,
        $3,
        $4::uuid,
        $5,
        $6::uuid,
        1.0,
        0.45,
        0,
        0,
        0,
        0,
        '1d',
        0,
        NULL,
        $7,
        NULL,
        false,
        false,
        false,
        NULL,
        NULL,
        NULL,
        NULL,
        now(),
        now()
      )
      `,
      [
        randomUUID(),
        userId,
        scenario.entryType === "word" ? "meaning" : "phrase_sense",
        scenario.resolvedTargetId,
        scenario.entryType,
        scenario.resolvedEntryId,
        `manual_prompt_type:${scenario.expectedPromptType}`,
      ],
    );
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }

  return {
    entryType: scenario.entryType,
    entryId: scenario.resolvedEntryId,
    displayText: scenario.displayText,
    expectedScheduleLabel: "Tomorrow",
  };
};

export const seedLegacyDuplicateReviewQueueFixture = async (
  userId: string,
): Promise<LegacyDuplicateReviewQueueFixture> => {
  const resolvedScenarios = await ensureScenarioCatalog();
  const firstScenario = resolvedScenarios.find((item) => item.key === "confidence-check");
  const secondScenario = resolvedScenarios.find((item) => item.key === "sentence-gap");
  if (!firstScenario || !secondScenario) {
    throw new Error("Missing review scenario definitions for legacy duplicate queue fixture");
  }

  const client = await connectClient();
  const now = new Date();
  const createdAt = new Date(now.getTime() - 60 * 60 * 1000);
  const reviewedAt = new Date(now.getTime() - 24 * 60 * 60 * 1000);

  try {
    await client.query("BEGIN");
    await upsertUserPreferences(client, userId);
    await client.query(`DELETE FROM entry_review_states WHERE user_id = $1::uuid`, [userId]);
    await upsertLearnerStatus(client, userId, firstScenario, "learning");
    await upsertLearnerStatus(client, userId, secondScenario, "learning");
    await insertReviewQueueState(client, userId, firstScenario, {
      scenarioKey: firstScenario.key,
      status: "learning",
      nextDueAt: now,
      lastReviewedAt: reviewedAt,
      srsBucket: "1d",
    });
    await insertReviewQueueState(client, userId, secondScenario, {
      scenarioKey: secondScenario.key,
      status: "learning",
      nextDueAt: now,
      lastReviewedAt: reviewedAt,
      srsBucket: "1d",
    });

    for (const scenario of [firstScenario, secondScenario]) {
      await client.query(
        `
        INSERT INTO entry_review_states (
          id,
          user_id,
          target_type,
          target_id,
          entry_type,
          entry_id,
          stability,
          difficulty,
          success_streak,
          lapse_count,
          exposure_count,
          times_remembered,
          srs_bucket,
          cadence_step,
          last_prompt_type,
          last_submission_prompt_id,
          last_outcome,
          is_fragile,
          is_suspended,
          relearning,
          relearning_trigger,
          recheck_due_at,
          last_reviewed_at,
          next_due_at,
          created_at,
          updated_at
        )
        VALUES (
          $1::uuid,
          $2::uuid,
          NULL,
          NULL,
          $3,
          $4::uuid,
          1.0,
          0.45,
          0,
          0,
          0,
          0,
          '1d',
          0,
          NULL,
          $5,
          NULL,
          false,
          false,
          false,
          NULL,
          NULL,
          NULL,
          NULL,
          $6::timestamptz,
          $7::timestamptz
        )
        `,
        [
          randomUUID(),
          userId,
          scenario.entryType,
          scenario.resolvedEntryId,
          `manual_prompt_type:${scenario.expectedPromptType}`,
          createdAt.toISOString(),
          createdAt.toISOString(),
        ],
      );
    }
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }

  return {
    bucket: "1d",
    visibleTexts: [firstScenario.displayText, secondScenario.displayText],
  };
};

export const forceScenarioDueNow = async (
  userId: string,
  scenarioKey: string,
): Promise<void> => {
  const resolvedScenarios = await ensureScenarioCatalog();
  const scenario = resolvedScenarios.find((item) => item.key === scenarioKey);

  if (!scenario) {
    throw new Error(`Missing review scenario definition for ${scenarioKey}`);
  }

  const client = await connectClient();

  try {
    await client.query("BEGIN");
    await client.query(
      `
      UPDATE entry_review_states
      SET
        next_due_at = now() - interval '1 minute',
        recheck_due_at = NULL,
        relearning = false,
        relearning_trigger = NULL,
        is_suspended = false,
        last_prompt_type = $4,
        last_submission_prompt_id = $5,
        updated_at = now()
      WHERE user_id = $1::uuid
        AND entry_type = $2
        AND entry_id = $3::uuid
      `,
      [
        userId,
        scenario.entryType,
        scenario.resolvedEntryId,
        scenario.expectedPromptType,
        `manual_prompt_type:${scenario.expectedPromptType}`,
      ],
    );
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
};

export const updateReviewScenarioTimezone = async (
  userId: string,
  timezone: string,
): Promise<void> => {
  const client = await connectClient();

  try {
    await client.query(
      `
      UPDATE user_preferences
      SET timezone = $2, updated_at = now()
      WHERE user_id = $1::uuid
      `,
      [userId, timezone],
    );
  } finally {
    await client.end();
  }
};

export const fetchReviewScenarioStateSnapshot = async (
  userId: string,
  scenarioKey: string,
): Promise<ReviewScenarioStateSnapshot> => {
  const resolvedScenarios = await ensureScenarioCatalog();
  const scenario = resolvedScenarios.find((item) => item.key === scenarioKey);

  if (!scenario) {
    throw new Error(`Missing review scenario definition for ${scenarioKey}`);
  }

  const client = await connectClient();

  try {
    const result = await client.query<{
      id: string;
      due_review_date: string | null;
      min_due_at_utc: string | null;
      next_due_at: string | null;
      recheck_due_at: string | null;
      last_reviewed_at: string | null;
      last_outcome: string | null;
    }>(
      `
      SELECT
        id::text AS id,
        due_review_date::text AS due_review_date,
        min_due_at_utc::text AS min_due_at_utc,
        next_due_at::text AS next_due_at,
        recheck_due_at::text AS recheck_due_at,
        last_reviewed_at::text AS last_reviewed_at,
        last_outcome
      FROM entry_review_states
      WHERE user_id = $1::uuid
        AND entry_type = $2
        AND entry_id = $3::uuid
      `,
      [userId, scenario.entryType, scenario.resolvedEntryId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new Error(`Missing review state for ${scenarioKey}`);
    }
    return {
      queueItemId: row.id,
      dueReviewDate: row.due_review_date,
      minDueAtUtc: row.min_due_at_utc,
      nextDueAt: row.next_due_at,
      recheckDueAt: row.recheck_due_at,
      lastReviewedAt: row.last_reviewed_at,
      lastOutcome: row.last_outcome,
    };
  } finally {
    await client.end();
  }
};
