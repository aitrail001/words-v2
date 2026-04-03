import { apiClient } from "@/lib/api-client";

export type AdminImportJobDetail = {
  id: string;
  user_id: string;
  import_source_id: string | null;
  word_list_id: string | null;
  status: string;
  source_filename: string;
  source_hash: string;
  list_name: string;
  list_description: string | null;
  total_items: number;
  processed_items: number;
  progress_stage: string | null;
  progress_total: number;
  progress_completed: number;
  progress_current_label: string | null;
  matched_entry_count: number;
  created_count: number;
  skipped_count: number;
  not_found_count: number;
  not_found_words: string[] | null;
  error_count: number;
  error_message: string | null;
  source_title: string | null;
  source_author: string | null;
  source_publisher: string | null;
  source_language: string | null;
  source_identifier: string | null;
  source_published_year: number | null;
  source_isbn: string | null;
  cache_available: boolean;
  cache_deleted: boolean;
  cache_deleted_at: string | null;
  cache_deleted_by_user_id: string | null;
  cache_deleted_message: string | null;
  from_cache: boolean;
  processing_duration_seconds: number | null;
  total_entries_extracted: number;
  word_entry_count: number;
  phrase_entry_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export const getAdminImportJob = async (jobId: string): Promise<AdminImportJobDetail> =>
  apiClient.get(`/admin/import-jobs/${jobId}`);
