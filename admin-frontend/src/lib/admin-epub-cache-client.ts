import { apiClient } from "@/lib/api-client";

export type AdminImportSourceSummary = {
  id: string;
  source_type: string;
  source_hash_sha256: string;
  title: string | null;
  author: string | null;
  publisher: string | null;
  language: string | null;
  source_identifier: string | null;
  published_year: number | null;
  isbn: string | null;
  status: string;
  matched_entry_count: number;
  created_at: string;
  processed_at: string | null;
  deleted_at: string | null;
  deleted_by_user_id: string | null;
  deletion_reason: string | null;
  first_imported_at: string | null;
  first_imported_by_user_id: string | null;
  first_imported_by_email: string | null;
  first_imported_by_role: string | null;
  processing_duration_seconds: number | null;
  source_filename: string | null;
  total_jobs: number;
  cache_hit_count: number;
  last_reused_at: string | null;
  last_reused_by_user_id: string | null;
  last_reused_by_email: string | null;
  last_reused_by_role: string | null;
};

export type AdminImportSourceListResponse = {
  total: number;
  items: AdminImportSourceSummary[];
};

export type AdminImportSourceJob = {
  id: string;
  user_id: string;
  user_email: string | null;
  user_role: string | null;
  import_batch_id: string | null;
  job_origin: string;
  status: string;
  source_filename: string;
  list_name: string;
  matched_entry_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  from_cache: boolean;
  processing_duration_seconds: number | null;
};

export type AdminImportSourceJobsResponse = {
  total: number;
  items: AdminImportSourceJob[];
};

export const listAdminImportSources = async (params?: {
  q?: string;
  status?: string;
  sort?: string;
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}): Promise<AdminImportSourceListResponse> => {
  const query = new URLSearchParams();
  if (params?.q) query.set("q", params.q);
  if (params?.status) query.set("status", params.status);
  if (params?.sort) query.set("sort", params.sort);
  if (params?.order) query.set("order", params.order);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiClient.get<AdminImportSourceListResponse>(`/admin/import-sources${suffix}`);
};

export const getAdminImportSource = async (sourceId: string): Promise<AdminImportSourceSummary> =>
  apiClient.get<AdminImportSourceSummary>(`/admin/import-sources/${sourceId}`);

export const listAdminImportSourceJobs = async (
  sourceId: string,
  params?: { from_cache?: "all" | "true" | "false"; job_origin?: string; limit?: number; offset?: number },
): Promise<AdminImportSourceJobsResponse> => {
  const query = new URLSearchParams();
  if (params?.from_cache) query.set("from_cache", params.from_cache);
  if (params?.job_origin) query.set("job_origin", params.job_origin);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiClient.get<AdminImportSourceJobsResponse>(`/admin/import-sources/${sourceId}/jobs${suffix}`);
};

export const listAdminImportSourceEntries = async (
  sourceId: string,
  params?: Record<string, string | number | undefined>,
): Promise<{ total: number; items: Array<Record<string, unknown>> }> => {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiClient.get<{ total: number; items: Array<Record<string, unknown>> }>(
    `/admin/import-sources/${sourceId}/entries${suffix}`,
  );
};

export const deleteAdminImportSourceCache = async (
  sourceId: string,
  params?: { deleteMode?: "cache_only" | "cache_only_and_delete_orphan_jobs"; deletionReason?: string },
): Promise<{ source_id: string; deleted_entry_count: number; deleted_orphan_job_count: number; delete_mode: string }> => {
  const query = new URLSearchParams();
  if (params?.deleteMode) query.set("delete_mode", params.deleteMode);
  if (params?.deletionReason) query.set("deletion_reason", params.deletionReason);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiClient.delete(`/admin/import-sources/${sourceId}${suffix}`);
};

export const bulkDeleteAdminImportSources = async (
  sourceIds: string[],
  params?: { deleteMode?: "cache_only" | "cache_only_and_delete_orphan_jobs"; deletionReason?: string },
): Promise<{ delete_mode: string; deleted: Array<{ source_id: string; deleted_entry_count: number; deleted_orphan_job_count: number }> }> =>
  apiClient.post("/admin/import-sources/bulk-delete", {
    source_ids: sourceIds,
    delete_mode: params?.deleteMode ?? "cache_only",
    deletion_reason: params?.deletionReason,
  });
