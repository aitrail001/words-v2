import { apiClient } from "@/lib/api-client";

export type LexiconImportRowSummary = {
  row_count: number;
  word_count: number;
  phrase_count: number;
  reference_count: number;
};

export type LexiconImportSummary = Record<string, number>;

export type LexiconImportResult = {
  artifact_filename: string;
  input_path: string;
  row_summary: LexiconImportRowSummary;
  import_summary: LexiconImportSummary | null;
  error_samples?: Array<{ entry: string; error: string }>;
};

export type LexiconImportJob = {
  id: string;
  artifact_filename: string;
  input_path: string;
  source_type: string;
  source_reference: string | null;
  language: string;
  conflict_mode: "fail" | "skip" | "upsert";
  error_mode: "fail_fast" | "continue";
  status: "queued" | "running" | "completed" | "failed";
  row_summary: LexiconImportRowSummary;
  import_summary: LexiconImportSummary | null;
  total_rows: number;
  completed_rows: number;
  remaining_rows: number;
  current_entry: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type LexiconImportRequest = {
  inputPath: string;
  sourceType: string;
  sourceReference?: string;
  language?: string;
  conflictMode?: "fail" | "skip" | "upsert";
  errorMode?: "fail_fast" | "continue";
};

export type LexiconVoiceImportRowSummary = {
  row_count: number;
  generated_count: number;
  existing_count: number;
  failed_count: number;
};

export type LexiconVoiceImportResult = {
  artifact_filename: string;
  input_path: string;
  row_summary: LexiconVoiceImportRowSummary;
  import_summary: LexiconImportSummary | null;
  error_samples?: Array<{ entry: string; error: string }>;
};

export const dryRunLexiconImport = (input: LexiconImportRequest): Promise<LexiconImportResult> =>
  apiClient.post<LexiconImportResult>("/lexicon-imports/dry-run", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
    conflict_mode: input.conflictMode ?? "fail",
    error_mode: input.errorMode ?? "fail_fast",
  });

export const runLexiconImport = (input: LexiconImportRequest): Promise<LexiconImportJob> =>
  apiClient.post<LexiconImportJob>("/lexicon-imports/run", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
    conflict_mode: input.conflictMode ?? "fail",
    error_mode: input.errorMode ?? "fail_fast",
  });

export const getLexiconImportJob = (jobId: string): Promise<LexiconImportJob> =>
  apiClient.get<LexiconImportJob>(`/lexicon-imports/jobs/${jobId}`);

export const dryRunVoiceImport = (input: LexiconImportRequest): Promise<LexiconVoiceImportResult> =>
  apiClient.post<LexiconVoiceImportResult>("/lexicon-imports/voice-dry-run", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
    conflict_mode: input.conflictMode ?? "fail",
    error_mode: input.errorMode ?? "fail_fast",
  });
