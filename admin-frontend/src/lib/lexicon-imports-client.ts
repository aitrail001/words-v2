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

export const runLexiconImport = (input: LexiconImportRequest): Promise<LexiconImportResult> =>
  apiClient.post<LexiconImportResult>("/lexicon-imports/run", {
    input_path: input.inputPath,
    source_type: input.sourceType,
    source_reference: input.sourceReference,
    language: input.language ?? "en",
  });
