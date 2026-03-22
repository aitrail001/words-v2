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

export const listLexiconOpsSnapshots = (): Promise<LexiconOpsSnapshotSummary[]> =>
  apiClient.get<LexiconOpsSnapshotSummary[]>("/lexicon-ops/snapshots");

export const getLexiconOpsSnapshot = (snapshotName: string): Promise<LexiconOpsSnapshotDetail> =>
  apiClient.get<LexiconOpsSnapshotDetail>(`/lexicon-ops/snapshots/${encodeURIComponent(snapshotName)}`);
