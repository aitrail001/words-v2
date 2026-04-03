import { apiClient } from "@/lib/api-client";

export type AdminImportBatchSummary = {
  id: string;
  created_by_user_id: string;
  created_by_email?: string | null;
  batch_type: string;
  name: string | null;
  created_at: string;
  total_jobs?: number;
  completed_jobs?: number;
  failed_jobs?: number;
  active_jobs?: number;
};

export type AdminImportBatchJob = {
  id: string;
  status: string;
  source_filename: string;
  import_source_id: string | null;
  job_origin?: string;
  from_cache: boolean;
  matched_entry_count?: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export const createAdminEpubImportBatch = async (input: {
  files: File[];
  batchName?: string;
}): Promise<{ batch: AdminImportBatchSummary; jobs: AdminImportBatchJob[]; failures?: Array<{ source_filename: string; error: string }> }> => {
  const formData = new FormData();
  for (const file of input.files) {
    formData.append("files", file);
  }
  if (input.batchName?.trim()) {
    formData.set("batch_name", input.batchName.trim());
  }
  return apiClient.post("/admin/import-batches/epub", formData);
};

export const listAdminImportBatches = async (params?: {
  limit?: number;
  offset?: number;
}): Promise<{ total: number; items: AdminImportBatchSummary[] }> => {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiClient.get(`/admin/import-batches${suffix}`);
};

export const getAdminImportBatch = async (batchId: string): Promise<AdminImportBatchSummary> =>
  apiClient.get(`/admin/import-batches/${batchId}`);

export const listAdminImportBatchJobs = async (
  batchId: string,
  params?: { limit?: number; offset?: number },
): Promise<{ total: number; items: AdminImportBatchJob[] }> => {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiClient.get(`/admin/import-batches/${batchId}/jobs${suffix}`);
};
