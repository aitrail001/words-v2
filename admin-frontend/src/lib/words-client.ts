import { apiClient } from "@/lib/api-client";

export type WordSearchResult = {
  id: string;
  word: string;
  language: string;
  phonetic: string | null;
  frequency_rank: number | null;
};

export type MeaningExample = {
  id: string;
  sentence: string;
  difficulty: string | null;
  order_index: number;
  source: string | null;
  confidence: number | null;
  enrichment_run_id: string | null;
};

export type WordRelation = {
  id: string;
  relation_type: string;
  related_word: string;
  related_word_id: string | null;
  source: string | null;
  confidence: number | null;
  enrichment_run_id: string | null;
};

export type LexiconEnrichmentRun = {
  id: string;
  enrichment_job_id: string;
  generator_provider: string | null;
  generator_model: string | null;
  validator_provider: string | null;
  validator_model: string | null;
  prompt_version: string | null;
  prompt_hash: string | null;
  verdict: string | null;
  confidence: number | null;
  token_input: number | null;
  token_output: number | null;
  estimated_cost: number | null;
  created_at: string;
};

export type EnrichedMeaning = {
  id: string;
  definition: string;
  part_of_speech: string | null;
  example_sentence: string | null;
  order_index: number;
  wn_synset_id: string | null;
  primary_domain: string | null;
  secondary_domains: string[] | null;
  register?: string | null;
  grammar_patterns: string[] | null;
  usage_note: string | null;
  learner_generated_at: string | null;
  examples: MeaningExample[];
  relations: WordRelation[];
};

export type WordEnrichmentDetail = {
  id: string;
  word: string;
  language: string;
  phonetic: string | null;
  frequency_rank: number | null;
  phonetic_source: string | null;
  phonetic_confidence: number | null;
  phonetic_enrichment_run_id: string | null;
  cefr_level: string | null;
  part_of_speech: string[] | null;
  confusable_words: Array<Record<string, string>> | null;
  learner_generated_at: string | null;
  meanings: EnrichedMeaning[];
  enrichment_runs: LexiconEnrichmentRun[];
};

export const searchWords = (query: string): Promise<WordSearchResult[]> =>
  apiClient.get<WordSearchResult[]>(`/words/search?q=${encodeURIComponent(query)}`);

export const getWordEnrichmentDetail = (wordId: string): Promise<WordEnrichmentDetail> =>
  apiClient.get<WordEnrichmentDetail>(`/words/${wordId}/enrichment`);
