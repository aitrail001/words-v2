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
};

export type LexiconImportJob = {
  id: string;
  artifact_filename: string;
  input_path: string;
  source_type: string;
  source_reference: string | null;
  language: string;
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
};

export const dryRunLexiconImport = (input: LexiconImportRequest): Promise<LexiconImportResult> =>
  apiClient.post<LexiconImportResult>("/lexicon-imports/dry-run", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
  });

export const runLexiconImport = (input: LexiconImportRequest): Promise<LexiconImportJob> =>
  apiClient.post<LexiconImportJob>("/lexicon-imports/run", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
  });

export const getLexiconImportJob = (jobId: string): Promise<LexiconImportJob> =>
  apiClient.get<LexiconImportJob>(`/lexicon-imports/jobs/${jobId}`);
