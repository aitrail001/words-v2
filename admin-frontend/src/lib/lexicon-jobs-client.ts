import { apiClient } from "@/lib/api-client";

export type LexiconJobStatus = "queued" | "running" | "completed" | "failed";

export type LexiconJob = {
  id: string;
  created_by: string | null;
  job_type: "import_db" | "jsonl_materialize" | "compiled_materialize" | "compiled_review_bulk_update";
  status: LexiconJobStatus;
  target_key: string;
  request_payload: Record<string, unknown>;
  result_payload: Record<string, unknown> | null;
  progress_total: number;
  progress_completed: number;
  progress_current_label: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type CreateImportDbLexiconJobInput = {
  inputPath: string;
  sourceType: string;
  sourceReference?: string;
  language?: string;
};

export type CreateJsonlMaterializeLexiconJobInput = {
  artifactPath: string;
  decisionsPath?: string;
  outputDir?: string;
};

export type CreateCompiledMaterializeLexiconJobInput = {
  batchId: string;
  outputDir?: string;
};

export type CreateCompiledReviewBulkUpdateLexiconJobInput = {
  batchId: string;
  reviewStatus: "pending" | "approved" | "rejected";
  decisionReason?: string;
  scope?: "all_pending";
};

export const createImportDbLexiconJob = (
  input: CreateImportDbLexiconJobInput,
): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>("/lexicon-jobs/import-db", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
  });

export const createJsonlMaterializeLexiconJob = (
  input: CreateJsonlMaterializeLexiconJobInput,
): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>("/lexicon-jobs/jsonl-materialize", {
    artifact_path: input.artifactPath,
    decisions_path: input.decisionsPath,
    output_dir: input.outputDir,
  });

export const createCompiledMaterializeLexiconJob = (
  input: CreateCompiledMaterializeLexiconJobInput,
): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>("/lexicon-jobs/compiled-materialize", {
    batch_id: input.batchId,
    output_dir: input.outputDir,
  });

export const createCompiledReviewBulkUpdateLexiconJob = (
  input: CreateCompiledReviewBulkUpdateLexiconJobInput,
): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>("/lexicon-jobs/compiled-review-bulk-update", {
    batch_id: input.batchId,
    review_status: input.reviewStatus,
    decision_reason: input.decisionReason,
    scope: input.scope ?? "all_pending",
  });

export const getLexiconJob = (jobId: string): Promise<LexiconJob> =>
  apiClient.get<LexiconJob>(`/lexicon-jobs/${jobId}`);
