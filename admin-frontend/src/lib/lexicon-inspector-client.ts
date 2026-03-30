import { apiClient } from "@/lib/api-client";

export type LexiconInspectorFamily = "word" | "phrase" | "reference";
export type LexiconInspectorFamilyFilter = "all" | LexiconInspectorFamily;
export type LexiconInspectorSort = "updated_desc" | "rank_asc" | "alpha_asc";

export type LexiconInspectorListEntry = {
  id: string;
  family: LexiconInspectorFamily;
  display_text: string;
  normalized_form: string | null;
  language: string;
  source_reference: string | null;
  cefr_level: string | null;
  frequency_rank: number | null;
  secondary_label: string | null;
  created_at: string | null;
};

export type LexiconInspectorListResponse = {
  items: LexiconInspectorListEntry[];
  total: number;
  family: LexiconInspectorFamilyFilter;
  q: string | null;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type LexiconInspectorWordDetail = {
  family: "word";
  id: string;
  display_text: string;
  normalized_form: string;
  language: string;
  cefr_level: string | null;
  frequency_rank: number | null;
  phonetics: Record<string, unknown> | null;
  phonetic: string | null;
  phonetic_source: string | null;
  phonetic_confidence: number | null;
  learner_part_of_speech: string[] | null;
  confusable_words: Array<Record<string, unknown>> | null;
  word_forms: Record<string, unknown> | null;
  source_type: string | null;
  source_reference: string | null;
  learner_generated_at: string | null;
  created_at: string | null;
  meanings: Array<{
    id: string;
    definition: string;
    part_of_speech: string | null;
    primary_domain: string | null;
    secondary_domains: string[] | null;
    register_label: string | null;
    grammar_patterns: string[] | null;
    usage_note: string | null;
    example_sentence: string | null;
    source: string | null;
    source_reference: string | null;
    learner_generated_at: string | null;
    order_index: number;
    examples: Array<{ id: string; sentence: string; difficulty: string | null; order_index: number }>;
    relations: Array<{ id: string; relation_type: string; related_word: string }>;
    translations: Array<{ id: string; language: string; translation: string }>;
  }>;
  enrichment_runs: Array<{ id: string; generator_model: string | null; validator_model: string | null; prompt_version: string | null; verdict: string | null; created_at: string }>;
  voice_assets: Array<{
    id: string;
    content_scope: string;
    meaning_id: string | null;
    meaning_example_id: string | null;
    locale: string;
    voice_role: string;
    provider: string;
    family: string;
    voice_id: string;
    profile_key: string;
    audio_format: string;
    mime_type: string | null;
    playback_url: string;
    playback_route_kind: string;
    status: string;
    generated_at: string | null;
    primary_target_kind: string;
    primary_target_base: string;
  }>;
  voice_paths: Record<string, {
    playback_url: string;
    resolved_target_kind: string;
    resolved_target_base: string;
  } | null>;
};

export type LexiconInspectorPhraseDetail = {
  family: "phrase";
  id: string;
  display_text: string;
  normalized_form: string;
  language: string;
  cefr_level: string | null;
  source_type: string | null;
  source_reference: string | null;
  phrase_kind: string;
  register_label: string | null;
  brief_usage_note: string | null;
  confidence_score: number | null;
  generated_at: string | null;
  seed_metadata: Record<string, unknown> | null;
  compiled_payload: Record<string, unknown> | null;
  senses: Array<{
    sense_id: string | null;
    definition: string;
    part_of_speech: string | null;
    grammar_patterns: string[] | null;
    usage_note: string | null;
    examples: Array<{ id: string; sentence: string; difficulty: string | null; order_index: number }>;
    translations: Array<{ locale: string; definition: string | null; usage_note: string | null; examples: string[] }>;
  }>;
  voice_assets: Array<{
    id: string;
    content_scope: string;
    meaning_id: string | null;
    meaning_example_id: string | null;
    locale: string;
    voice_role: string;
    provider: string;
    family: string;
    voice_id: string;
    profile_key: string;
    audio_format: string;
    mime_type: string | null;
    playback_url: string;
    playback_route_kind: string;
    status: string;
    generated_at: string | null;
    primary_target_kind: string;
    primary_target_base: string;
  }>;
  voice_paths: Record<string, {
    playback_url: string;
    resolved_target_kind: string;
    resolved_target_base: string;
  } | null>;
  created_at: string | null;
};

export type LexiconInspectorReferenceDetail = {
  family: "reference";
  id: string;
  display_text: string;
  normalized_form: string;
  language: string;
  source_reference: string | null;
  reference_type: string;
  translation_mode: string;
  brief_description: string;
  pronunciation: string;
  learner_tip: string | null;
  created_at: string | null;
  localizations: Array<{ id: string; locale: string; display_form: string; brief_description: string | null; translation_mode: string | null }>;
};

export type LexiconInspectorDetail =
  | LexiconInspectorWordDetail
  | LexiconInspectorPhraseDetail
  | LexiconInspectorReferenceDetail;

export const browseLexiconInspectorEntries = (input: {
  family: LexiconInspectorFamilyFilter;
  q?: string;
  sort: LexiconInspectorSort;
  limit: number;
  offset: number;
}): Promise<LexiconInspectorListResponse> => {
  const params = new URLSearchParams({
    family: input.family,
    sort: input.sort,
    limit: String(input.limit),
    offset: String(input.offset),
  });
  if (input.q?.trim()) params.set("q", input.q.trim());
  return apiClient.get<LexiconInspectorListResponse>(`/lexicon-inspector/entries?${params.toString()}`);
};

export const getLexiconInspectorDetail = (
  family: LexiconInspectorFamily,
  id: string,
): Promise<LexiconInspectorDetail> =>
  apiClient.get<LexiconInspectorDetail>(`/lexicon-inspector/entries/${family}/${id}`);
