import { apiClient } from "@/lib/api-client";

export type LexiconReviewStatus = "pending" | "approved" | "rejected" | "needs_edit";

export type LexiconReviewBatch = {
  id: string;
  user_id: string;
  status: string;
  source_filename: string;
  source_hash: string;
  source_type: string | null;
  source_reference: string | null;
  snapshot_id: string | null;
  total_items: number;
  review_required_count: number;
  auto_accepted_count: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type LexiconCandidateMetadata = Record<string, unknown> & {
  wn_synset_id?: string;
  canonical_gloss?: string;
  canonical_label?: string;
  label?: string;
  part_of_speech?: string;
  score?: number;
  selection_score?: number;
  lemma_count?: number;
  flags?: string[];
};

export type LexiconReviewCandidateEntry = {
  wn_synset_id: string;
  canonical_label: string | null;
  gloss: string | null;
  definition: string | null;
  part_of_speech: string | null;
  rank_hint: number | null;
  reason_hint: string | null;
  deterministic_selected: boolean;
  reranked_selected: boolean;
  review_override_selected: boolean;
  selected: boolean;
};

export type LexiconReviewItem = {
  id: string;
  batch_id: string;
  lexeme_id: string;
  lemma: string;
  language: string;
  wordfreq_rank: number | null;
  risk_band: string;
  selection_risk_score: number;
  deterministic_selected_wn_synset_ids: string[];
  reranked_selected_wn_synset_ids: string[] | null;
  selected_wn_synset_ids: string[];
  selected_source: string;
  candidate_metadata: LexiconCandidateMetadata[];
  candidate_entries: LexiconReviewCandidateEntry[];
  auto_accepted: boolean;
  review_required: boolean;
  review_status: LexiconReviewStatus;
  review_override_wn_synset_ids: string[] | null;
  review_comment: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  row_payload: Record<string, unknown>;
  created_at: string;
};

export type LexiconReviewItemUpdateRequest = {
  review_status: LexiconReviewStatus;
  review_comment?: string | null;
  review_override_wn_synset_ids?: string[] | null;
};

export type LexiconReviewBatchPublishPreviewItem = {
  item_id: string;
  lemma: string;
  language: string;
  action: string;
  selected_synset_ids: string[];
  existing_lexicon_meaning_count: number;
  new_meaning_count: number;
  warnings: string[];
};

export type LexiconReviewBatchPublishPreview = {
  batch_id: string;
  publishable_item_count: number;
  created_word_count: number;
  updated_word_count: number;
  replaced_meaning_count: number;
  created_meaning_count: number;
  skipped_item_count: number;
  items: LexiconReviewBatchPublishPreviewItem[];
};

export type LexiconReviewBatchPublishResult = {
  batch_id: string;
  status: string;
  published_item_count: number;
  published_word_count: number;
  updated_word_count: number;
  replaced_meaning_count: number;
  created_meaning_count: number;
  published_at: string;
};

export type ListLexiconReviewItemsParams = {
  reviewStatus?: LexiconReviewStatus;
  reviewRequired?: boolean;
  riskBand?: string;
};

const buildQuery = (params: Record<string, string | number | boolean | null | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
};

export const listLexiconReviewBatches = (): Promise<LexiconReviewBatch[]> =>
  apiClient.get<LexiconReviewBatch[]>("/lexicon-reviews/batches");

export const getLexiconReviewBatch = (batchId: string): Promise<LexiconReviewBatch> =>
  apiClient.get<LexiconReviewBatch>(`/lexicon-reviews/batches/${batchId}`);

export const listLexiconReviewItems = (
  batchId: string,
  params: ListLexiconReviewItemsParams = {},
): Promise<LexiconReviewItem[]> => {
  const query = buildQuery({
    review_status: params.reviewStatus,
    review_required: params.reviewRequired,
    risk_band: params.riskBand,
  });
  return apiClient.get<LexiconReviewItem[]>(`/lexicon-reviews/batches/${batchId}/items${query}`);
};

export const updateLexiconReviewItem = (
  itemId: string,
  payload: LexiconReviewItemUpdateRequest,
): Promise<LexiconReviewItem> =>
  apiClient.patch<LexiconReviewItem>(`/lexicon-reviews/items/${itemId}`, payload);

export const previewLexiconReviewBatchPublish = (
  batchId: string,
): Promise<LexiconReviewBatchPublishPreview> =>
  apiClient.get<LexiconReviewBatchPublishPreview>(`/lexicon-reviews/batches/${batchId}/publish-preview`);

export const publishLexiconReviewBatch = (
  batchId: string,
): Promise<LexiconReviewBatchPublishResult> =>
  apiClient.post<LexiconReviewBatchPublishResult>(`/lexicon-reviews/batches/${batchId}/publish`);

export const importLexiconReviewBatch = async (input: {
  file: File;
  sourceType?: string;
  sourceReference?: string;
}): Promise<LexiconReviewBatch> => {
  const formData = new FormData();
  formData.append("file", input.file);
  if (input.sourceType) formData.append("source_type", input.sourceType);
  if (input.sourceReference) formData.append("source_reference", input.sourceReference);
  return apiClient.post<LexiconReviewBatch>("/lexicon-reviews/batches/import", formData);
};
