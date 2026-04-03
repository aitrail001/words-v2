import { ApiError, apiClient } from "@/lib/api-client";

export type LexiconJobStatus = "queued" | "running" | "cancel_requested" | "completed" | "failed" | "cancelled";

export type LexiconJobProgressTiming = {
  queue_wait_ms?: number | null;
  elapsed_ms?: number | null;
  validation_elapsed_ms?: number | null;
  import_elapsed_ms?: number | null;
  finalization_elapsed_ms?: number | null;
  orchestration_elapsed_ms?: number | null;
};

export type LexiconJob = {
  id: string;
  created_by: string | null;
  job_type: "import_db" | "voice_import_db" | "jsonl_materialize" | "compiled_materialize" | "compiled_review_bulk_update";
  status: LexiconJobStatus;
  target_key: string;
  request_payload: Record<string, unknown>;
  result_payload: Record<string, unknown> | null;
  progress_total: number;
  progress_completed: number;
  progress_current_label: string | null;
  progress_summary: {
    phase: string;
    phase_started_at_ms?: number;
    total: number;
    validated: number;
    imported: number;
    skipped: number;
    failed: number;
    to_validate: number;
    to_import: number;
  } | null;
  progress_timing?: LexiconJobProgressTiming | null;
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
  conflictMode?: "fail" | "skip" | "upsert";
  errorMode?: "fail_fast" | "continue";
  importExecutionMode?: "continuation" | "single_task";
  importRowChunkSize?: number;
  importRowCommitSize?: number;
  voiceGroupChunkSize?: number;
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

const normalizeLexiconJobIds = (jobIds: string[]): string[] =>
  Array.from(new Set(jobIds.map((jobId) => jobId.trim()).filter(Boolean)));

const parseStoredLexiconJobIds = (value: string | null): string[] => {
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return normalizeLexiconJobIds(parsed.filter((item): item is string => typeof item === "string"));
  } catch {
    return [];
  }
};

export const readLexiconActiveJobIds = (storageKey: string): string[] => {
  if (typeof window === "undefined") {
    return [];
  }
  return parseStoredLexiconJobIds(window.localStorage.getItem(storageKey));
};

export const writeLexiconActiveJobIds = (storageKey: string, jobIds: string[]): string[] => {
  if (typeof window === "undefined") {
    return normalizeLexiconJobIds(jobIds);
  }
  const normalizedJobIds = normalizeLexiconJobIds(jobIds);
  if (normalizedJobIds.length > 0) {
    window.localStorage.setItem(storageKey, JSON.stringify(normalizedJobIds));
  } else {
    window.localStorage.removeItem(storageKey);
  }
  return normalizedJobIds;
};

export const addLexiconActiveJobId = (storageKey: string, jobId: string): string[] =>
  writeLexiconActiveJobIds(storageKey, [...readLexiconActiveJobIds(storageKey), jobId]);

export const removeLexiconActiveJobId = (storageKey: string, jobId: string): string[] =>
  writeLexiconActiveJobIds(
    storageKey,
    readLexiconActiveJobIds(storageKey).filter((existingJobId) => existingJobId !== jobId),
  );

export const isLexiconJobActive = (job: Pick<LexiconJob, "status">): boolean =>
  job.status === "queued" || job.status === "running" || job.status === "cancel_requested";

export const upsertLexiconJob = (jobs: LexiconJob[], nextJob: LexiconJob): LexiconJob[] => {
  const remainingJobs = jobs.filter((job) => job.id !== nextJob.id);
  return [nextJob, ...remainingJobs];
};

const isProgressTimingRecord = (value: unknown): value is LexiconJobProgressTiming =>
  typeof value === "object" && value !== null;

export const getLexiconJobProgressTiming = (
  job: Pick<LexiconJob, "progress_timing" | "request_payload">,
): LexiconJobProgressTiming | null => {
  if (isProgressTimingRecord(job.progress_timing)) {
    return job.progress_timing;
  }
  const nestedTiming = job.request_payload.progress_timing;
  return isProgressTimingRecord(nestedTiming) ? nestedTiming : null;
};

export const formatLexiconJobDuration = (milliseconds: number | null | undefined): string | null => {
  if (milliseconds === null || milliseconds === undefined || !Number.isFinite(milliseconds) || milliseconds < 0) {
    return null;
  }
  if (milliseconds < 1000) {
    return `${Math.round(milliseconds)}ms`;
  }
  const totalSeconds = milliseconds / 1000;
  if (totalSeconds < 60) {
    return `${totalSeconds < 10 ? totalSeconds.toFixed(1) : Math.round(totalSeconds)}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  if (seconds === 0) {
    return `${minutes}m`;
  }
  return `${minutes}m ${seconds}s`;
};

export const getLexiconJobConflictMessage = (jobLabel: string, error: unknown): string | null => {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return null;
  }
  const detail = (error.message && error.message !== "Request failed: 409")
    ? error.message.trim()
    : "";
  if (detail) {
    return detail;
  }
  return `Another ${jobLabel} job already holds this source reference lock. Wait for the queued or running job to finish before retrying.`;
};

export const createImportDbLexiconJob = (
  input: CreateImportDbLexiconJobInput,
): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>("/lexicon-jobs/import-db", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
    conflict_mode: input.conflictMode ?? "fail",
    error_mode: input.errorMode ?? "fail_fast",
    import_execution_mode: input.importExecutionMode ?? "continuation",
    import_row_chunk_size: input.importRowChunkSize,
    import_row_commit_size: input.importRowCommitSize,
  });

export const createVoiceImportDbLexiconJob = (
  input: CreateImportDbLexiconJobInput,
): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>("/lexicon-jobs/voice-import-db", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
    conflict_mode: input.conflictMode ?? "fail",
    error_mode: input.errorMode ?? "fail_fast",
    voice_group_chunk_size: input.voiceGroupChunkSize,
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

export const cancelLexiconJob = (jobId: string): Promise<LexiconJob> =>
  apiClient.post<LexiconJob>(`/lexicon-jobs/${jobId}/cancel`, {});

export const listLexiconJobs = (input?: {
  jobType?: LexiconJob["job_type"];
  limit?: number;
}): Promise<LexiconJob[]> => {
  const params = new URLSearchParams();
  if (input?.jobType) params.set("job_type", input.jobType);
  if (input?.limit) params.set("limit", String(input.limit));
  const query = params.toString();
  return apiClient.get<LexiconJob[]>(`/lexicon-jobs${query ? `?${query}` : ""}`);
};
