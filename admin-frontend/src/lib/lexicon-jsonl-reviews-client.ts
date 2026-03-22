import { apiClient } from "@/lib/api-client";
import { readAccessToken } from "@/lib/auth-session";

export type LexiconJsonlReviewItem = {
  entry_id: string;
  entry_type: string;
  normalized_form: string | null;
  display_text: string;
  entity_category?: string | null;
  language?: string;
  frequency_rank?: number | null;
  cefr_level?: string | null;
  review_priority?: "normal" | "warning";
  warning_count?: number;
  warning_labels?: string[];
  review_summary?: {
    sense_count: number;
    form_variant_count: number;
    confusable_count: number;
    provenance_sources: string[];
    primary_definition: string | null;
    primary_example: string | null;
  };
  review_status: "pending" | "approved" | "rejected";
  decision_reason: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  compiled_payload: Record<string, unknown>;
  compiled_payload_sha256?: string;
};

export type LexiconJsonlReviewSession = {
  artifact_filename: string;
  artifact_path: string;
  artifact_sha256?: string;
  decisions_path: string;
  output_dir?: string | null;
  total_items: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  items: LexiconJsonlReviewItem[];
};

export type LoadLexiconJsonlReviewSessionInput = {
  artifactPath: string;
  decisionsPath?: string;
  outputDir?: string;
};

export type UpdateLexiconJsonlReviewItemInput = {
  artifactPath: string;
  decisionsPath?: string;
  reviewStatus: "pending" | "approved" | "rejected";
  decisionReason?: string | null;
};

export type BulkUpdateLexiconJsonlReviewItemsInput = {
  artifactPath: string;
  decisionsPath?: string;
  reviewStatus: "pending" | "approved" | "rejected";
  decisionReason?: string | null;
};

export type MaterializeLexiconJsonlReviewOutputsInput = {
  artifactPath: string;
  decisionsPath?: string;
  outputDir?: string;
};

export type LexiconJsonlReviewMaterializeResult = {
  artifact_sha256?: string;
  decision_count?: number;
  approved_count: number;
  rejected_count: number;
  regenerate_count: number;
  decisions_output_path: string;
  approved_output_path: string;
  rejected_output_path: string;
  regenerate_output_path: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function downloadReviewOutput(kind: "approved" | "rejected" | "regenerate" | "decisions", input: MaterializeLexiconJsonlReviewOutputsInput): Promise<string> {
  const token = readAccessToken();
  const response = await fetch(`${API_BASE_URL}/lexicon-jsonl-reviews/download/${kind}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      artifact_path: input.artifactPath,
      decisions_path: input.decisionsPath,
      output_dir: input.outputDir,
    }),
  });
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }
  return response.text();
}

export const loadLexiconJsonlReviewSession = (
  input: LoadLexiconJsonlReviewSessionInput,
): Promise<LexiconJsonlReviewSession> =>
  apiClient.post<LexiconJsonlReviewSession>("/lexicon-jsonl-reviews/load", {
    artifact_path: input.artifactPath,
    decisions_path: input.decisionsPath,
    output_dir: input.outputDir,
  });

export const updateLexiconJsonlReviewItem = (
  entryId: string,
  input: UpdateLexiconJsonlReviewItemInput,
): Promise<LexiconJsonlReviewItem> =>
  apiClient.patch<LexiconJsonlReviewItem>(`/lexicon-jsonl-reviews/items/${encodeURIComponent(entryId)}`, {
    artifact_path: input.artifactPath,
    decisions_path: input.decisionsPath,
    review_status: input.reviewStatus,
    decision_reason: input.decisionReason,
  });

export const materializeLexiconJsonlReviewOutputs = (
  input: MaterializeLexiconJsonlReviewOutputsInput,
): Promise<LexiconJsonlReviewMaterializeResult> =>
  apiClient.post<LexiconJsonlReviewMaterializeResult>("/lexicon-jsonl-reviews/materialize", {
    artifact_path: input.artifactPath,
    decisions_path: input.decisionsPath,
    output_dir: input.outputDir,
  });

export const bulkUpdateLexiconJsonlReviewItems = (
  input: BulkUpdateLexiconJsonlReviewItemsInput,
): Promise<LexiconJsonlReviewSession> =>
  apiClient.post<LexiconJsonlReviewSession>("/lexicon-jsonl-reviews/bulk-update", {
    artifact_path: input.artifactPath,
    decisions_path: input.decisionsPath,
    review_status: input.reviewStatus,
    decision_reason: input.decisionReason,
  });

export const downloadApprovedLexiconJsonlReviewOutput = (input: MaterializeLexiconJsonlReviewOutputsInput): Promise<string> =>
  downloadReviewOutput("approved", input);

export const downloadRejectedLexiconJsonlReviewOutput = (input: MaterializeLexiconJsonlReviewOutputsInput): Promise<string> =>
  downloadReviewOutput("rejected", input);

export const downloadRegenerateLexiconJsonlReviewOutput = (input: MaterializeLexiconJsonlReviewOutputsInput): Promise<string> =>
  downloadReviewOutput("regenerate", input);

export const downloadDecisionLexiconJsonlReviewOutput = (input: MaterializeLexiconJsonlReviewOutputsInput): Promise<string> =>
  downloadReviewOutput("decisions", input);
