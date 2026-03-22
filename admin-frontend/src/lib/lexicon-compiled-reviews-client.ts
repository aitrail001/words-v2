import { apiClient } from "@/lib/api-client";
import { readAccessToken } from "@/lib/auth-session";

export type LexiconCompiledReviewBatch = {
  id: string;
  artifact_family: string;
  artifact_filename: string;
  artifact_sha256: string;
  artifact_row_count: number;
  compiled_schema_version: string;
  snapshot_id: string | null;
  source_type: string | null;
  source_reference: string | null;
  status: string;
  total_items: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type LexiconCompiledReviewItem = {
  id: string;
  batch_id: string;
  entry_id: string;
  entry_type: string;
  normalized_form: string | null;
  display_text: string;
  entity_category: string | null;
  language: string;
  frequency_rank: number | null;
  cefr_level: string | null;
  review_status: "pending" | "approved" | "rejected";
  review_priority: number;
  validator_status: string | null;
  validator_issues: Array<Record<string, unknown>> | null;
  qc_status: string | null;
  qc_score: number | null;
  qc_issues: Array<Record<string, unknown>> | null;
  regen_requested: boolean;
  import_eligible: boolean;
  decision_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  compiled_payload: Record<string, unknown>;
  compiled_payload_sha256: string;
  created_at: string;
  updated_at: string;
};

export type LexiconCompiledReviewItemUpdateRequest = {
  review_status: "pending" | "approved" | "rejected";
  decision_reason?: string | null;
};

export type LexiconCompiledReviewMaterializeResult = {
  decision_count: number;
  approved_count: number;
  rejected_count: number;
  regenerate_count: number;
  decisions_output_path: string;
  approved_output_path: string;
  rejected_output_path: string;
  regenerate_output_path: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function downloadExport(path: string): Promise<string> {
  const token = readAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status}`);
  }
  return response.text();
}

export const listLexiconCompiledReviewBatches = (): Promise<LexiconCompiledReviewBatch[]> =>
  apiClient.get<LexiconCompiledReviewBatch[]>("/lexicon-compiled-reviews/batches");

export const getLexiconCompiledReviewBatch = (batchId: string): Promise<LexiconCompiledReviewBatch> =>
  apiClient.get<LexiconCompiledReviewBatch>(`/lexicon-compiled-reviews/batches/${batchId}`);

export const deleteLexiconCompiledReviewBatch = (batchId: string): Promise<void> =>
  apiClient.delete<void>(`/lexicon-compiled-reviews/batches/${batchId}`);

export const listLexiconCompiledReviewItems = (batchId: string): Promise<LexiconCompiledReviewItem[]> =>
  apiClient.get<LexiconCompiledReviewItem[]>(`/lexicon-compiled-reviews/batches/${batchId}/items`);

export const updateLexiconCompiledReviewItem = (
  itemId: string,
  payload: LexiconCompiledReviewItemUpdateRequest,
): Promise<LexiconCompiledReviewItem> =>
  apiClient.patch<LexiconCompiledReviewItem>(`/lexicon-compiled-reviews/items/${itemId}`, payload);

export const importLexiconCompiledReviewBatch = async (input: {
  file: File;
  sourceType?: string;
  sourceReference?: string;
}): Promise<LexiconCompiledReviewBatch> => {
  const formData = new FormData();
  formData.append("file", input.file);
  if (input.sourceType) formData.append("source_type", input.sourceType);
  if (input.sourceReference) formData.append("source_reference", input.sourceReference);
  return apiClient.post<LexiconCompiledReviewBatch>("/lexicon-compiled-reviews/batches/import", formData);
};

export const importLexiconCompiledReviewBatchByPath = (input: {
  artifactPath: string;
  sourceType?: string;
  sourceReference?: string;
}): Promise<LexiconCompiledReviewBatch> =>
  apiClient.post<LexiconCompiledReviewBatch>("/lexicon-compiled-reviews/batches/import-by-path", {
    artifact_path: input.artifactPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
  });

export const downloadApprovedCompiledReviewExport = (batchId: string): Promise<string> =>
  downloadExport(`/lexicon-compiled-reviews/batches/${batchId}/export/approved`);

export const downloadRejectedCompiledReviewExport = (batchId: string): Promise<string> =>
  downloadExport(`/lexicon-compiled-reviews/batches/${batchId}/export/rejected`);

export const downloadRegenerateCompiledReviewExport = (batchId: string): Promise<string> =>
  downloadExport(`/lexicon-compiled-reviews/batches/${batchId}/export/regenerate`);

export const downloadCompiledReviewDecisionsExport = (batchId: string): Promise<string> =>
  downloadExport(`/lexicon-compiled-reviews/batches/${batchId}/export/decisions`);

export const materializeLexiconCompiledReviewOutputs = (
  batchId: string,
  input?: { outputDir?: string },
): Promise<LexiconCompiledReviewMaterializeResult> =>
  apiClient.post<LexiconCompiledReviewMaterializeResult>(`/lexicon-compiled-reviews/batches/${batchId}/materialize`, {
    output_dir: input?.outputDir,
  });
