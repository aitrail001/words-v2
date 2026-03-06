import { apiClient } from "@/lib/api-client";

export type ImportJobStatus = "queued" | "processing" | "completed" | "failed";

export type ImportJob = {
  id: string;
  user_id: string;
  book_id: string | null;
  word_list_id: string | null;
  status: ImportJobStatus;
  source_filename: string;
  source_hash: string;
  list_name: string;
  list_description: string | null;
  total_items: number;
  processed_items: number;
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

export type WordList = {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  source_type: string | null;
  source_reference: string | null;
  book_id: string | null;
  created_at: string;
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

export const listWordLists = async (): Promise<WordList[]> =>
  apiClient.get<WordList[]>("/word-lists");

export const isImportJobTerminal = (status: ImportJobStatus): boolean =>
  status === "completed" || status === "failed";

export const getImportProgressPercent = (job: Pick<ImportJob, "total_items" | "processed_items">): number => {
  if (job.total_items <= 0) {
    return 0;
  }

  const rawPercent = Math.round((job.processed_items / job.total_items) * 100);
  return Math.max(0, Math.min(100, rawPercent));
};
