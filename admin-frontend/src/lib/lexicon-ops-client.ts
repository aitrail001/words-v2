import { apiClient } from "@/lib/api-client";

export type LexiconOpsSnapshotSummary = {
  snapshot: string;
  snapshot_path: string;
  snapshot_id: string | null;
  updated_at: string;
  artifact_counts: Record<string, number>;
  has_enrichments: boolean;
  has_compiled_export: boolean;
  has_ambiguous_forms: boolean;
  workflow_stage: string;
  recommended_action: string;
  preferred_review_artifact_path: string | null;
  preferred_import_artifact_path: string | null;
  outside_portal_steps: string[];
};

export type LexiconOpsSnapshotArtifact = {
  file_name: string;
  exists: boolean;
  size_bytes: number | null;
  modified_at: string | null;
  row_count: number | null;
  read_error: string | null;
};

export type LexiconOpsSnapshotDetail = LexiconOpsSnapshotSummary & {
  artifacts: LexiconOpsSnapshotArtifact[];
};

export type RewriteLexiconVoiceStorageRequest = {
  source_reference?: string;
  policy_ids?: string[];
  provider?: string;
  family?: string;
  locale?: string;
  storage_kind: string;
  storage_base: string;
  dry_run?: boolean;
};

export type RewriteLexiconVoiceStorageResponse = {
  matched_count: number;
  updated_count: number;
  dry_run: boolean;
  storage_kind: string;
  storage_base: string;
  fallback_storage_kind: string | null;
  fallback_storage_base: string | null;
};

export type LexiconVoiceStorageSummaryGroup = {
  storage_kind: string;
  storage_base: string;
  asset_count: number;
};

export type LexiconVoiceStorageSummary = {
  source_reference: string;
  asset_count: number;
  groups: LexiconVoiceStorageSummaryGroup[];
};

export type LexiconVoiceStoragePolicy = {
  id: string;
  policy_key: string;
  content_scope: string;
  primary_storage_kind: string;
  primary_storage_base: string;
  fallback_storage_kind: string | null;
  fallback_storage_base: string | null;
  asset_count: number;
};

export type LexiconVoiceRunSummary = {
  run_name: string;
  run_path: string;
  updated_at: string;
  planned_count: number;
  generated_count: number;
  existing_count: number;
  failed_count: number;
};

export type LexiconVoiceRunDetail = LexiconVoiceRunSummary & {
  locale_counts: Record<string, number>;
  voice_role_counts: Record<string, number>;
  content_scope_counts: Record<string, number>;
  source_references: string[];
  artifacts: Record<string, string>;
  latest_manifest_rows: Record<string, unknown>[];
  latest_error_rows: Record<string, unknown>[];
};

export const listLexiconOpsSnapshots = (): Promise<LexiconOpsSnapshotSummary[]> =>
  apiClient.get<LexiconOpsSnapshotSummary[]>("/lexicon-ops/snapshots");

export const getLexiconOpsSnapshot = (snapshotName: string): Promise<LexiconOpsSnapshotDetail> =>
  apiClient.get<LexiconOpsSnapshotDetail>(`/lexicon-ops/snapshots/${encodeURIComponent(snapshotName)}`);

export const rewriteLexiconVoiceStorage = (
  payload: RewriteLexiconVoiceStorageRequest,
): Promise<RewriteLexiconVoiceStorageResponse> =>
  apiClient.post<RewriteLexiconVoiceStorageResponse>("/lexicon-ops/voice-storage/rewrite", payload);

export const getLexiconVoiceStorageSummary = (
  sourceReference: string,
): Promise<LexiconVoiceStorageSummary> =>
  apiClient.get<LexiconVoiceStorageSummary>(`/lexicon-ops/voice-storage/summary?source_reference=${encodeURIComponent(sourceReference)}`);

export const getLexiconVoiceStoragePolicies = (
  sourceReference?: string,
): Promise<LexiconVoiceStoragePolicy[]> =>
  apiClient.get<LexiconVoiceStoragePolicy[]>(
    `/lexicon-ops/voice-storage/policies${sourceReference ? `?source_reference=${encodeURIComponent(sourceReference)}` : ""}`,
  );

export const getLexiconVoiceRuns = (): Promise<LexiconVoiceRunSummary[]> =>
  apiClient.get<LexiconVoiceRunSummary[]>("/lexicon-ops/voice-runs");

export const getLexiconVoiceRunDetail = (
  runName: string,
): Promise<LexiconVoiceRunDetail> =>
  apiClient.get<LexiconVoiceRunDetail>(`/lexicon-ops/voice-runs/${encodeURIComponent(runName)}`);
