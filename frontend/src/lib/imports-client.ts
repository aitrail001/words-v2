import { apiClient } from "@/lib/api-client";
import type { KnowledgeEntryType } from "@/lib/knowledge-map-client";

export type ImportJobStatus = "queued" | "processing" | "completed" | "failed";

export type ImportJob = {
  id: string;
  user_id: string;
  import_source_id: string | null;
  word_list_id: string | null;
  status: ImportJobStatus;
  source_filename: string;
  source_hash: string;
  list_name: string;
  list_description: string | null;
  total_items: number;
  processed_items: number;
  matched_entry_count: number;
  created_count: number;
  skipped_count: number;
  not_found_count: number;
  not_found_words: string[] | null;
  error_count: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type ReviewEntry = {
  source_entry_row_id?: string;
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  normalized_form: string | null;
  frequency_count: number;
  browse_rank: number | null;
  cefr_level: string | null;
  phrase_kind: string | null;
  primary_part_of_speech?: string | null;
};

export type ReviewEntriesResponse = {
  total: number;
  items: ReviewEntry[];
};

export type BulkResolveResponse = {
  found_entries: ReviewEntry[];
  ambiguous_entries: string[];
  not_found_count: number;
};

export type WordList = {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  source_type: string | null;
  source_reference: string | null;
  created_at: string;
};

export type WordListItem = {
  id: string;
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string | null;
  normalized_form: string | null;
  browse_rank: number | null;
  cefr_level: string | null;
  phrase_kind: string | null;
  part_of_speech: string | null;
  frequency_count: number;
  added_at: string;
};

export type WordListDetail = WordList & {
  items: WordListItem[];
};

export type WordListDetailQuery = {
  q?: string;
  sort?: "alpha" | "rank" | "rank_desc";
};

export const createWordListImport = async (
  file: File,
  listName?: string,
): Promise<ImportJob> => {
  const formData = new FormData();
  formData.set("file", file);
  if (listName?.trim()) {
    formData.set("list_name", listName.trim());
  }

  return apiClient.post<ImportJob>("/word-lists/import", formData);
};

export const getImportJob = async (jobId: string): Promise<ImportJob> =>
  apiClient.get<ImportJob>(`/import-jobs/${jobId}`);

export const getImportEntries = async (
  jobId: string,
  params: Record<string, string | number | undefined>,
): Promise<ReviewEntriesResponse> => {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  return apiClient.get<ReviewEntriesResponse>(`/import-jobs/${jobId}/entries?${query.toString()}`);
};

export const createListFromImport = async (
  jobId: string,
  payload: {
    name: string;
    description?: string;
    selected_entries: Array<{ entry_type: KnowledgeEntryType; entry_id: string }>;
  },
): Promise<WordList> =>
  apiClient.post<WordList>(`/import-jobs/${jobId}/word-lists`, payload);

export const listWordLists = async (): Promise<WordList[]> =>
  apiClient.get<WordList[]>("/word-lists");

export const getWordList = async (
  wordListId: string,
  query?: WordListDetailQuery,
): Promise<WordListDetail> => {
  const params = new URLSearchParams();
  if (query?.q?.trim()) {
    params.set("q", query.q.trim());
  }
  if (query?.sort) {
    params.set("sort", query.sort);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiClient.get<WordListDetail>(`/word-lists/${wordListId}${suffix}`);
};

export const updateWordList = async (
  wordListId: string,
  payload: { name?: string; description?: string | null },
): Promise<WordList> =>
  apiClient.patch<WordList>(`/word-lists/${wordListId}`, payload);

export const deleteWordList = async (wordListId: string): Promise<void> =>
  apiClient.delete<void>(`/word-lists/${wordListId}`);

export const resolveEntries = async (rawText: string): Promise<BulkResolveResponse> =>
  apiClient.post<BulkResolveResponse>("/word-lists/resolve-entries", { raw_text: rawText });

export const addWordListItem = async (
  wordListId: string,
  payload: {
    entry_type: KnowledgeEntryType;
    entry_id: string;
    frequency_count?: number;
  },
): Promise<WordListItem> =>
  apiClient.post<WordListItem>(`/word-lists/${wordListId}/items`, payload);

export const bulkAddWordListEntries = async (
  wordListId: string,
  payload: {
    selected_entries: Array<{ entry_type: KnowledgeEntryType; entry_id: string }>;
  },
): Promise<WordListDetail> =>
  apiClient.post<WordListDetail>(`/word-lists/${wordListId}/bulk-add`, payload);

export const deleteWordListItem = async (
  wordListId: string,
  itemId: string,
): Promise<void> =>
  apiClient.delete<void>(`/word-lists/${wordListId}/items/${itemId}`);

export const isImportJobTerminal = (status: ImportJobStatus): boolean =>
  status === "completed" || status === "failed";

export const getImportProgressPercent = (
  job: Pick<ImportJob, "total_items" | "processed_items">,
): number => {
  if (job.total_items <= 0) {
    return 0;
  }

  const rawPercent = Math.round((job.processed_items / job.total_items) * 100);
  return Math.max(0, Math.min(100, rawPercent));
};
