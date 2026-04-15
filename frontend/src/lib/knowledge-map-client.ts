import { apiClient } from "@/lib/api-client";

export type KnowledgeStatus = "undecided" | "to_learn" | "learning" | "known";
export type KnowledgeEntryType = "word" | "phrase";

export type LearnerVoiceAccent = "us" | "uk" | "au";
export type LearnerPronunciations = Partial<Record<LearnerVoiceAccent, string>>;

export type LearnerVoicePlaybackLocale = {
  playback_url: string;
  locale: string;
  relative_path?: string | null;
};

export type LearnerVoicePlaybackPayload = {
  preferred_locale?: LearnerVoiceAccent | null;
  preferred_playback_url?: string | null;
  locales?: Partial<Record<LearnerVoiceAccent, LearnerVoicePlaybackLocale>> & Record<string, LearnerVoicePlaybackLocale>;
};

export type LearnerVoiceAsset = {
  id: string;
  content_scope: string;
  meaning_id?: string | null;
  meaning_example_id?: string | null;
  phrase_sense_id?: string | null;
  phrase_sense_example_id?: string | null;
  locale: string;
  voice_role?: string;
  provider?: string;
  family?: string;
  voice_id?: string;
  profile_key?: string;
  audio_format?: string;
  mime_type?: string | null;
  speaking_rate?: number | null;
  pitch_semitones?: number | null;
  lead_ms?: number;
  tail_ms?: number;
  effects_profile_id?: string | null;
  playback_url: string;
  storage_kind?: string;
  storage_base?: string;
  relative_path?: string;
  status?: string;
  generation_error?: string | null;
  generated_at?: string | null;
};

export type KnowledgeMapEntrySummary = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  normalized_form: string | null;
  browse_rank: number;
  status: KnowledgeStatus;
  cefr_level: string | null;
  pronunciation: string | null;
  pronunciations?: LearnerPronunciations;
  translation: string | null;
  primary_definition: string | null;
  primary_example?: string | null;
  primary_example_translation?: string | null;
  part_of_speech: string | null;
  phrase_kind: string | null;
  voice_assets?: LearnerVoiceAsset[];
  voice?: LearnerVoicePlaybackPayload | null;
};

export type KnowledgeMapOverview = {
  bucket_size: number;
  total_entries: number;
  ranges: Array<{
    range_start: number;
    range_end: number;
    total_entries: number;
    counts: Record<KnowledgeStatus, number>;
  }>;
};

export type KnowledgeMapDashboard = {
  total_entries: number;
  counts: Record<KnowledgeStatus, number>;
  discovery_range_start: number | null;
  discovery_range_end: number | null;
  discovery_entry: {
    entry_type: KnowledgeEntryType;
    entry_id: string;
    display_text: string;
    browse_rank: number;
    status: KnowledgeStatus;
  } | null;
  next_learn_entry: {
    entry_type: KnowledgeEntryType;
    entry_id: string;
    display_text: string;
    browse_rank: number;
    status: KnowledgeStatus;
  } | null;
};

export type ReviewQueueStats = {
  total_items: number;
  due_items: number;
  review_count: number;
  correct_count: number;
  accuracy: number;
};

export type AuthUserProfile = {
  id: string;
  email: string;
  role: string;
  tier: string;
  is_active: boolean;
};

export type ReviewQueueBucket =
  | "1d"
  | "2d"
  | "3d"
  | "5d"
  | "7d"
  | "14d"
  | "30d"
  | "90d"
  | "180d";

export type ReviewQueueBucketSort = "next_review_at" | "last_reviewed_at" | "text";
export type ReviewQueueBucketOrder = "asc" | "desc";

export type ReviewQueueSummaryBucket = {
  bucket: ReviewQueueBucket;
  count: number;
  has_due_now?: boolean;
};

export type ReviewQueueSummaryResponse = {
  generated_at: string;
  total_count: number;
  groups: ReviewQueueSummaryBucket[];
};

export type ReviewQueueItem = {
  queue_item_id: string;
  entry_id: string;
  entry_type: KnowledgeEntryType;
  text: string;
  status: KnowledgeStatus;
  next_review_at: string | null;
  due_review_date?: string | null;
  min_due_at_utc?: string | null;
  last_reviewed_at: string | null;
  bucket?: ReviewQueueBucket;
  success_streak: number;
  lapse_count: number;
  times_remembered: number;
  exposure_count: number;
  history: ReviewQueueHistoryEvent[];
};

export type ReviewQueueHistoryEvent = {
  id: string;
  reviewed_at: string;
  outcome: string;
  prompt_type: string;
  prompt_family?: string | null;
  scheduled_by?: string | null;
  scheduled_interval_days?: number | null;
};

export type ReviewQueueBucketDetailResponse = {
  generated_at: string;
  bucket: ReviewQueueBucket;
  count: number;
  sort: ReviewQueueBucketSort;
  order: ReviewQueueBucketOrder;
  items: ReviewQueueItem[];
};

export type GroupedReviewQueueItem = ReviewQueueItem;

export type GroupedReviewQueueGroup = {
  bucket: ReviewQueueBucket;
  count: number;
  items: GroupedReviewQueueItem[];
};

export type GroupedReviewQueueResponse = {
  generated_at: string;
  total_count: number;
  groups: GroupedReviewQueueGroup[];
};

export type DueGroupedReviewQueueGroup = {
  group_key: string;
  label: string;
  due_in_days: number;
  count: number;
  items: GroupedReviewQueueItem[];
};

export type DueGroupedReviewQueueResponse = {
  generated_at: string;
  total_count: number;
  groups: DueGroupedReviewQueueGroup[];
};

export type AdminReviewQueueItem = ReviewQueueItem & {
  target_type: string | null;
  target_id: string | null;
  recheck_due_at: string | null;
  next_due_at: string | null;
  last_outcome: string | null;
  relearning: boolean | null;
  relearning_trigger: string | null;
};

export type AdminReviewQueueSummaryResponse = {
  generated_at: string;
  total_count: number;
  groups: ReviewQueueSummaryBucket[];
  debug: {
    effective_now: string;
  };
};

export type AdminReviewQueueBucketDetailResponse = {
  generated_at: string;
  bucket: ReviewQueueBucket;
  count: number;
  sort: ReviewQueueBucketSort;
  order: ReviewQueueBucketOrder;
  items: AdminReviewQueueItem[];
  debug: {
    effective_now: string;
  };
};

export type AdminGroupedReviewQueueItem = AdminReviewQueueItem;

export type AdminGroupedReviewQueueGroup = {
  bucket: ReviewQueueBucket;
  count: number;
  items: AdminGroupedReviewQueueItem[];
};

export type AdminGroupedReviewQueueResponse = {
  generated_at: string;
  total_count: number;
  groups: AdminGroupedReviewQueueGroup[];
  debug: {
    effective_now: string;
  };
};

export type KnowledgeMapRange = {
  range_start: number;
  range_end: number;
  previous_range_start: number | null;
  next_range_start: number | null;
  items: KnowledgeMapEntrySummary[];
};

export type ReviewPromptOption = {
  option_id: string;
  label: string;
};

export type ReviewPromptPayload = {
  mode: string;
  prompt_type: string;
  prompt_token?: string | null;
  stem?: string | null;
  question: string;
  options?: ReviewPromptOption[];
  expected_input?: string | null;
  input_mode?: string | null;
  voice_placeholder_text?: string | null;
  sentence_masked?: string | null;
  source_entry_type?: KnowledgeEntryType | null;
  source_word_id?: string | null;
  source_meaning_id?: string | null;
  audio_state?: string;
  audio?: LearnerVoicePlaybackPayload | null;
};

export type ReviewDetailMeaning = {
  id: string;
  definition: string;
  example?: string | null;
  part_of_speech?: string | null;
};

export type ReviewDetailPayload = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  pronunciation?: string | null;
  pronunciations?: LearnerPronunciations;
  part_of_speech?: string | null;
  primary_definition?: string | null;
  primary_example?: string | null;
  meaning_count: number;
  remembered_count: number;
  pro_tip?: string | null;
  compare_with: string[];
  meanings: ReviewDetailMeaning[];
  audio_state?: string;
  audio?: LearnerVoicePlaybackPayload | null;
  coverage_summary?: string | null;
};

export type ReviewScheduleOption = {
  value: string;
  label: string;
  is_default: boolean;
};

export type EntryReviewQueue = {
  queue_item_id: string;
  next_review_at?: string | null;
  due_review_date?: string | null;
  min_due_at_utc?: string | null;
  recheck_due_at?: string | null;
  current_schedule_value: string;
  current_schedule_label: string;
  current_schedule_source?: string;
  schedule_options: ReviewScheduleOption[];
};

export type LearningStartCard = {
  queue_item_id: string | null;
  meaning_id: string;
  word: string;
  definition: string | null;
  prompt: ReviewPromptPayload;
  detail?: ReviewDetailPayload | null;
};

export type LearningStartResponse = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  entry_word: string;
  meaning_ids: string[];
  queue_item_ids: string[];
  cards: LearningStartCard[];
  requires_lookup_hint: boolean;
  detail?: ReviewDetailPayload | null;
  schedule_options?: ReviewScheduleOption[];
};

export type KnowledgeMapMeaning = {
  id: string;
  definition: string;
  localized_definition?: string | null;
  part_of_speech: string | null;
  usage_note?: string | null;
  localized_usage_note?: string | null;
  register?: string | null;
  primary_domain?: string | null;
  secondary_domains?: string[];
  grammar_patterns?: string[];
  synonyms?: Array<{
    text: string;
    target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  antonyms?: Array<{
    text: string;
    target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  collocations?: Array<{
    text: string;
    target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  examples: Array<{
    id: string;
    sentence: string;
    difficulty: string | null;
    translation?: string | null;
    linked_entries?: Array<{ text: string; entry_type: KnowledgeEntryType; entry_id: string }>;
  }>;
  translations: Array<{ id: string; language: string; translation: string; usage_note?: string | null; examples?: string[] }>;
  relations: Array<{ id: string; relation_type: string; related_word: string }>;
};

export type KnowledgeMapSense = {
  sense_id: string | null;
  definition: string;
  localized_definition?: string | null;
  part_of_speech: string | null;
  usage_note?: string | null;
  localized_usage_note?: string | null;
  register?: string | null;
  primary_domain?: string | null;
  secondary_domains?: string[];
  grammar_patterns?: string[];
  synonyms?: Array<{
    text: string;
    target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  antonyms?: Array<{
    text: string;
    target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  collocations?: Array<{
    text: string;
    target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  examples: Array<{
    id: string;
    sentence: string;
    difficulty: string | null;
    translation?: string | null;
    linked_entries?: Array<{ text: string; entry_type: KnowledgeEntryType; entry_id: string }>;
  }>;
};

export type KnowledgeMapEntryDetail = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  normalized_form: string | null;
  browse_rank: number;
  status: KnowledgeStatus;
  cefr_level: string | null;
  pronunciation: string | null;
  pronunciations?: LearnerPronunciations;
  translation: string | null;
  primary_definition: string | null;
  supported_translation_locales?: string[];
  voice_assets?: LearnerVoiceAsset[];
  voice?: LearnerVoicePlaybackPayload | null;
  forms?: {
    verb_forms: Record<string, string>;
    plural_forms: string[];
    derivations: Array<{
      text: string;
      target: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
    }>;
    comparative: string | null;
    superlative: string | null;
  } | null;
  meanings: KnowledgeMapMeaning[];
  senses: KnowledgeMapSense[];
  relation_groups: Array<{ relation_type: string; related_words: string[] }>;
  confusable_words: Array<{
    word: string;
    note: string | null;
    target?: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  }>;
  review_queue?: EntryReviewQueue | null;
  previous_entry: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
  next_entry: { entry_type: KnowledgeEntryType; entry_id: string; display_text: string } | null;
};

export type KnowledgeMapSearchHistoryList = {
  items: Array<{
    query: string;
    entry_type: KnowledgeEntryType | null;
    entry_id: string | null;
    last_searched_at: string;
  }>;
};

export type KnowledgeMapListStatus = "new" | "to_learn" | "learning" | "known";
export type KnowledgeMapListSort = "rank" | "alpha";
export type KnowledgeMapListOrder = "asc" | "desc";

export function normalizeLearnerTranslation(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed || trimmed === "Translation unavailable") {
    return null;
  }

  return trimmed;
}

export function resolveLearnerVoicePlaybackUrl(
  voice: LearnerVoicePlaybackPayload | null | undefined,
  accent: LearnerVoiceAccent,
): string | null {
  if (!voice) {
    return null;
  }

  const accentedLocale = voice.locales?.[accent];
  if (accentedLocale?.playback_url) {
    return accentedLocale.playback_url;
  }

  if (voice.preferred_playback_url) {
    return voice.preferred_playback_url;
  }

  const fallbackLocale = Object.values(voice.locales ?? {}).find(
    (locale): locale is LearnerVoicePlaybackLocale => Boolean(locale?.playback_url),
  );
  return fallbackLocale?.playback_url ?? null;
}

export const getKnowledgeMapOverview = (): Promise<KnowledgeMapOverview> =>
  apiClient.get<KnowledgeMapOverview>("/knowledge-map/overview");

export const getKnowledgeMapDashboard = (): Promise<KnowledgeMapDashboard> =>
  apiClient.get<KnowledgeMapDashboard>("/knowledge-map/dashboard");

export const getReviewQueueStats = (): Promise<ReviewQueueStats> =>
  apiClient.get<ReviewQueueStats>("/reviews/queue/stats");

export const getAuthUserProfile = (): Promise<AuthUserProfile> =>
  apiClient.get<AuthUserProfile>("/auth/me");

export const getReviewQueueSummary = (): Promise<ReviewQueueSummaryResponse> =>
  apiClient.get<ReviewQueueSummaryResponse>("/reviews/queue/summary");

export const getReviewQueueBucketDetail = (
  bucket: ReviewQueueBucket,
  sort: ReviewQueueBucketSort = "next_review_at",
  order: ReviewQueueBucketOrder = "asc",
): Promise<ReviewQueueBucketDetailResponse> => {
  const searchParams = new URLSearchParams();
  searchParams.set("sort", sort);
  searchParams.set("order", order);
  const query = searchParams.toString();
  return apiClient.get<ReviewQueueBucketDetailResponse>(
    `/reviews/queue/buckets/${bucket}${query ? `?${query}` : ""}`,
  );
};

export const getGroupedReviewQueue = (): Promise<GroupedReviewQueueResponse> =>
  apiClient.get<GroupedReviewQueueResponse>("/reviews/queue/grouped");

export const getGroupedReviewQueueByDue = (): Promise<DueGroupedReviewQueueResponse> =>
  apiClient.get<DueGroupedReviewQueueResponse>("/reviews/queue/grouped/by-due");

export const getAdminReviewQueueSummary = (
  effectiveNow?: string,
): Promise<AdminReviewQueueSummaryResponse> => {
  const searchParams = new URLSearchParams();
  if (effectiveNow) {
    searchParams.set("effective_now", effectiveNow);
  }
  const query = searchParams.toString();
  return apiClient.get<AdminReviewQueueSummaryResponse>(
    `/reviews/admin/queue/summary${query ? `?${query}` : ""}`,
  );
};

export const getAdminReviewQueueBucketDetail = (
  bucket: ReviewQueueBucket,
  options?: {
    effectiveNow?: string;
    sort?: "next_review_at" | "last_reviewed_at" | "text";
    order?: "asc" | "desc";
  },
): Promise<AdminReviewQueueBucketDetailResponse> => {
  const searchParams = new URLSearchParams();
  if (options?.effectiveNow) {
    searchParams.set("effective_now", options.effectiveNow);
  }
  if (options?.sort) {
    searchParams.set("sort", options.sort);
  }
  if (options?.order) {
    searchParams.set("order", options.order);
  }
  const query = searchParams.toString();
  return apiClient.get<AdminReviewQueueBucketDetailResponse>(
    `/reviews/admin/queue/buckets/${bucket}${query ? `?${query}` : ""}`,
  );
};

export const getAdminGroupedReviewQueue = (
  effectiveNow?: string,
): Promise<AdminGroupedReviewQueueResponse> => {
  const searchParams = new URLSearchParams();
  if (effectiveNow) {
    searchParams.set("effective_now", effectiveNow);
  }

  const query = searchParams.toString();
  return apiClient.get<AdminGroupedReviewQueueResponse>(
    `/reviews/admin/queue/grouped${query ? `?${query}` : ""}`,
  );
};

export const getKnowledgeMapRange = (rangeStart: number): Promise<KnowledgeMapRange> =>
  apiClient.get<KnowledgeMapRange>(`/knowledge-map/ranges/${rangeStart}`);

export const getKnowledgeMapEntryDetail = (
  entryType: KnowledgeEntryType,
  entryId: string,
): Promise<KnowledgeMapEntryDetail> =>
  apiClient.get<KnowledgeMapEntryDetail>(`/knowledge-map/entries/${entryType}/${entryId}`);

export const updateReviewQueueSchedule = (
  queueItemId: string,
  scheduleOverride: string,
): Promise<EntryReviewQueue> =>
  apiClient.put<EntryReviewQueue>(`/reviews/queue/${queueItemId}/schedule`, {
    schedule_override: scheduleOverride,
  });

export const updateKnowledgeEntryStatus = (
  entryType: KnowledgeEntryType,
  entryId: string,
  status: KnowledgeStatus,
): Promise<{ entry_type: KnowledgeEntryType; entry_id: string; status: KnowledgeStatus }> =>
  apiClient.put(`/knowledge-map/entries/${entryType}/${entryId}/status`, { status });

export const searchKnowledgeMap = (query: string): Promise<{ items: KnowledgeMapEntrySummary[] }> =>
  apiClient.get<{ items: KnowledgeMapEntrySummary[] }>(`/knowledge-map/search?q=${encodeURIComponent(query)}`);

export const startLearningEntry = (
  entryType: KnowledgeEntryType,
  entryId: string,
): Promise<LearningStartResponse> =>
  apiClient.post(`/reviews/entry/${entryType}/${entryId}/learning/start`);

export const getKnowledgeMapList = (params: {
  status: KnowledgeMapListStatus;
  q?: string;
  sort?: KnowledgeMapListSort;
  order?: KnowledgeMapListOrder;
  limit?: number;
}): Promise<{ items: KnowledgeMapEntrySummary[] }> => {
  const searchParams = new URLSearchParams();
  searchParams.set("status", params.status);
  if (params.q) {
    searchParams.set("q", params.q);
  }
  if (params.sort) {
    searchParams.set("sort", params.sort);
  }
  if (params.order) {
    searchParams.set("order", params.order);
  }
  if (params.limit) {
    searchParams.set("limit", String(params.limit));
  }
  return apiClient.get<{ items: KnowledgeMapEntrySummary[] }>(`/knowledge-map/list?${searchParams.toString()}`);
};

export const getKnowledgeMapSearchHistory = (): Promise<KnowledgeMapSearchHistoryList> =>
  apiClient.get<KnowledgeMapSearchHistoryList>("/knowledge-map/search-history");

export const createKnowledgeMapSearchHistory = (payload: {
  query: string;
  entry_type?: KnowledgeEntryType;
  entry_id?: string;
}): Promise<{ query: string; entry_type: KnowledgeEntryType | null; entry_id: string | null; last_searched_at?: string }> =>
  apiClient.post("/knowledge-map/search-history", payload);
